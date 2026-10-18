#!/usr/bin/env python3
"""Check the BOM / CPL against JLCPCB's own part data and rewrite cpl.csv.

Run with KiCad's Python after build_pcb.py. For every assembled part this
fetches (once, cached in ../../work/easyeda-cache) the EasyEDA symbol and
footprint JLC places from, then:
  * finds the rotation and origin that put JLC's footprint pads on ours, so
    cpl.csv carries JLC's convention instead of KiCad's (SOT-23, SOIC, TSSOP
    and polarised parts differ by 90/180 degrees);
  * fails when a pad lands more than TOL away (wrong package or size);
  * checks pin 1 / polarity by pad number (D5 cathode, C25 +, D4 cathode);
  * reports stock and Basic / Extended type (each Extended part adds a
    loading fee at JLC).
Writes cpl.csv and reports/jlc.json. Exit 1 on a mismatch.
"""
import csv, json, math, subprocess, sys, time
from pathlib import Path
import pcbnew as p

ROOT = Path(__file__).resolve().parent
CACHE = ROOT.parent.parent / 'work' / 'easyeda-cache'
U = 0.254                                # EasyEDA canvas unit, mm
# Pad-centre tolerance where JLC's land pattern differs from ours but the part
# still sits symmetrically: longer outward pads move the centres (U1, U7,
# SOD-323, L1, C25); U6's corner pads are L-shaped in TI's pattern. J2 follows
# the Shou Han drawing: its rear pad is 1.1 mm from the tip pad (1.4 mm in
# JLC's footprint) and its pads sit 3.85 mm off the plug axis (3.5 mm in
# JLC's). J2 is placed on its pegs instead (PEGGED), so the pad error is only
# reported.
TOL = {'U1': .3, 'U6': .25, 'U7': .25, 'D2': .2, 'D3': .2, 'D5': .2,
       'L1': .3, 'C25': .3, 'J2': .6}
# Parts with locating pegs: the CPL centre comes from the pegs, which must land
# in our NPTH holes (PJ-320D: 0.75 mm pegs in 1.0 mm holes, 0.125 mm play).
# A pad-average fit would shift J2 by the pad differences above.
PEGGED = {'J2': .05}
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126 Safari/537.36')
# KiCad pad -> JLC pad where the libraries number differently. PJ-320D: JLC 2
# is next to the opening, 1 is the lone rear (tip) pad.
PADMAP = {'J2': {'R2': '2', 'R1': '3', 'T': '4', 'S': '1'}}


def fetch(code, kind):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f'{code}.{kind}.json'
    if not f.exists():
        url = (f'https://easyeda.com/api/products/{code}/components?version=6.4.19.5'
               if kind == 'easyeda' else
               'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/'
               'smtGood/selectSmtComponentList')
        # curl, not urllib: it uses the system certificate store.
        cmd = ['curl', '-sSfL', '--max-time', '30', '-A', UA, '-o', str(f), url]
        if kind != 'easyeda':
            cmd[1:1] = ['-H', 'Content-Type: application/json', '-d',
                        json.dumps({'keyword': code, 'currentPage': 1, 'pageSize': 5})]
        # The API rate-limits bursts (HTTP 403): back off and retry.
        for wait in (5, 20, 60, 0):
            if subprocess.run(cmd, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(wait)
        else:
            raise SystemExit(f'cannot fetch {kind} data for {code}')
        time.sleep(1)
    return json.loads(f.read_text())


def jlc_pads(code):
    r = fetch(code, 'easyeda')['result']
    head = r['packageDetail']['dataStr']['head']
    ox, oy = float(head['x']), float(head['y'])
    pads, holes = {}, []
    for s in r['packageDetail']['dataStr']['shape']:
        if s.startswith('HOLE~'):
            f = s.split('~')
            holes.append(((float(f[1]) - ox) * U, -(float(f[2]) - oy) * U))
        if s.startswith('PAD~'):
            f = s.split('~')
            pts = [float(v) for v in f[10].split()] if f[10] else []
            if pts:
                cx, cy = sum(pts[0::2]) / len(pts[0::2]), sum(pts[1::2]) / len(pts[1::2])
            else:
                cx, cy = float(f[2]), float(f[3])
            # y up, relative to the package origin JLC places at Mid X / Mid Y
            pads.setdefault(f[8], []).append(((cx - ox) * U, -(cy - oy) * U))
    pins = {}
    for s in r['dataStr']['shape']:
        if s.startswith('P~'):
            seg = s.split('^^')
            pins[seg[4].split('~')[4]] = seg[3].split('~')[4]
    return r['title'], r['packageDetail']['title'], pads, pins, holes


def rot(v, deg):
    a = math.radians(deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


NAME = json.loads((ROOT / 'placement.json').read_text())['board']['name']
board = p.LoadBoard(str(ROOT / f'{NAME}.kicad_pcb'))
design = {d['ref']: d for d in json.loads((ROOT / 'design.json').read_text())}
results, rows, bad = {}, [], []
for f in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
    ref = f.GetReference()
    d = design[ref]
    if d['kind'] == 'mech' or d.get('dnp'):
        continue
    title, package, jp, pins, jholes = jlc_pads(d['lcsc'])
    ours = {}
    for a in f.Pads():
        n = PADMAP.get(ref, {}).get(a.GetNumber(), a.GetNumber())
        if n in jp and len(jp[n]) == 1:
            ours.setdefault(n, []).append((p.ToMM(a.GetPosition().x), -p.ToMM(a.GetPosition().y)))
    common = [n for n in ours if len(ours[n]) == 1]
    best = None
    for r in (0, 90, 180, 270):
        rp = {n: rot(jp[n][0], r) for n in common}
        tx = sum(ours[n][0][0] - rp[n][0] for n in common) / len(common)
        ty = sum(ours[n][0][1] - rp[n][1] for n in common) / len(common)
        err = max(math.dist(ours[n][0], (rp[n][0] + tx, rp[n][1] + ty)) for n in common)
        if best is None or err < best[0]:
            best = (err, r, tx, ty)
    err, r, tx, ty = best
    peg_err = None
    if ref in PEGGED:
        oh = [(p.ToMM(a.GetPosition().x), -p.ToMM(a.GetPosition().y))
              for a in f.Pads() if a.GetAttribute() == p.PAD_ATTRIB_NPTH]
        jh = [rot(h, r) for h in jholes]
        if len(oh) != len(jh) or not oh:
            raise SystemExit(f'{ref}: {len(oh)} NPTH holes here, {len(jh)} in JLC data')
        pair = [(o, min(jh, key=lambda h: math.dist(o, (h[0] + tx, h[1] + ty)))) for o in oh]
        tx = sum(o[0] - h[0] for o, h in pair) / len(pair)
        ty = sum(o[1] - h[1] for o, h in pair) / len(pair)
        peg_err = max(math.dist(o, (h[0] + tx, h[1] + ty)) for o, h in pair)
        err = max(math.dist(ours[n][0], (rot(jp[n][0], r)[0] + tx, rot(jp[n][0], r)[1] + ty))
                  for n in common)
    ok = (err <= TOL.get(ref, .1) and len(common) >= min(2, len(jp)) and
          (peg_err is None or peg_err <= PEGGED[ref]))
    if not ok:
        bad.append(ref)
    results[ref] = dict(lcsc=d['lcsc'], jlc_part=title, jlc_package=package,
                        pads_compared=len(common), max_pad_error_mm=round(err, 3),
                        kicad_rotation=d['rot'], jlc_rotation=r,
                        mid=[round(tx, 3), round(ty, 3)], pin_names=pins, ok=ok,
                        **({} if peg_err is None else {'max_peg_error_mm': round(peg_err, 3)}))
    rows.append([ref, f'{tx:.3f}', f'{ty:.3f}', 'Top', r])

# Polarity: the JLC pin behind our pad 1 must be the cathode / plus.
for ref, want in (('D4', 'K'), ('D5', 'C'), ('C25', '1')):
    got = results[ref]['pin_names'].get('1')
    if got != want:
        bad.append(f'{ref} pin 1 is {got}, want {want}')

# Stock and Basic / Extended.
need = {}
for d in design.values():
    if d['kind'] != 'mech' and not d.get('dnp'):
        need[d['lcsc']] = need.get(d['lcsc'], 0) + 1
stock = {}
for code, qty in sorted(need.items()):
    lst = (fetch(code, 'stock').get('data') or {}).get('componentPageInfo', {}).get('list') or []
    hit = next((c for c in lst if c.get('componentCode') == code), None)
    stock[code] = dict(per_board=qty, stock=hit and hit.get('stockCount'),
                       type=hit and ('Basic' if hit.get('componentLibraryType') == 'base'
                                     else 'Extended'))
with (ROOT / 'cpl.csv').open('w') as out:
    w = csv.writer(out)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    w.writerows(rows)
(ROOT / 'reports' / 'jlc.json').write_text(json.dumps(
    {'parts': results, 'stock': stock, 'problems': bad}, indent=1) + '\n')
ext = sorted(c for c, s in stock.items() if s['type'] == 'Extended')
low = sorted(c for c, s in stock.items() if not s['stock'] or s['stock'] < 100)
turned = sum(1 for v in results.values() if v['jlc_rotation'] != v['kicad_rotation'] % 360)
print(f'JLC footprints matched: {len(results) - len([b for b in bad if b in results])}'
      f' / {len(results)}; CPL rotations changed from KiCad: {turned}; '
      f'Extended parts: {len(ext)}; stock < 100: {low or "none"}')
if bad:
    print('PROBLEMS:', bad)
    sys.exit(1)
