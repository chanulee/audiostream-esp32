#!/usr/bin/env python3
"""Render the built board for visual review; compare with the previous build.

Run with KiCad's Python after make_board.sh. Writes renders/latest/:
  pcba-top/-bottom/-iso.png    3D, assembled (KiCad 3D models where they exist)
  bare-top/-bottom.png         3D, bare PCB (models stripped from a copy)
  assembly-top.png/.pdf        placement drawing: refs, values, pin 1, polarity
  layer-<L>.png                copper per layer (F.Cu, In1.Cu, In2.Cu, B.Cu)
  routing.png                  outer-layer routing coloured by net group
  diff-*.png                   what changed against renders/previous/
  index.html                   all of the above side by side, then the board's
                               version history (hardware/versions.json)
The run before this one moves to renders/previous/. It also rewrites
hardware/archive/index.html, the same history on its own.

  render_board.py                         the built board, full set
  render_board.py BOARD --out DIR [--2d]  any other board file (archived
                                          versions), no previous / diff
"""
import argparse, html, json, math, os, shutil, subprocess, sys
from pathlib import Path
import pcbnew as p
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
HW = ROOT.parent
NAME = json.loads((ROOT / 'placement.json').read_text())['board']['name']
ap = argparse.ArgumentParser()
ap.add_argument('board', nargs='?', default=str(ROOT / f'{NAME}.kicad_pcb'))
ap.add_argument('--out')
ap.add_argument('--2d', dest='only_2d', action='store_true')
args = ap.parse_args()
OUT = Path(args.out).resolve() if args.out else ROOT / 'renders' / 'latest'
CURRENT = args.out is None             # the live board: keep previous, diff
PREV = OUT.parent / 'previous'
CLI = next(c for c in [Path('/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli'),
                        Path(shutil.which('kicad-cli') or '/nonexistent')]
           if c.exists())
S = 40                     # px per mm for the 2D views
M = 1                      # margin around board + overhanging parts, mm
GROUPS = [                 # (label, colour, nets)
    ('power', (214, 64, 46), {'VBUS', '+5V', '+5V_DAC', 'SW', 'POWER_EN', 'OVLO',
                              'ILIM', 'DVDT'}),
    ('analog', (36, 150, 72), {'+3V3_A', 'DAC_L', 'DAC_R', 'LINE_L', 'LINE_R',
                               'VNEG', 'CAPP', 'CAPM', 'LDOO', 'XSMT'}),
    ('I2S', (38, 98, 214), {'BCLK', 'DATA', 'LRCLK'}),
    ('USB / UART', (150, 60, 190), {'USB_DP', 'USB_DM', 'UART_RX', 'UART_TX',
                                    'CC1', 'CC2'}),
    ('3V3 digital', (225, 140, 20), {'+3V3_D'}),
    ('GND', (90, 90, 90), {'GND'}),
]
OTHER = ('other', (20, 20, 20))


def colour(net):
    return next((c for _, c, nets in GROUPS if net in nets), OTHER[1])


def run(*args):
    subprocess.run([str(a) for a in args], check=True, capture_output=True)


pcb = Path(args.board).resolve()
board = p.LoadBoard(str(pcb))
TITLE = (board.GetTitleBlock().GetTitle() or pcb.stem) + (
    f' rev {board.GetTitleBlock().GetRevision()}' if board.GetTitleBlock().GetRevision() else '')
if CURRENT and OUT.exists():
    shutil.rmtree(PREV, ignore_errors=True)
    OUT.rename(PREV)
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)

# --- 3D: assembled and bare ------------------------------------------------
def render3d(board_file, prefix, iso):
    for side in ('top', 'bottom'):
        run(CLI, 'pcb', 'render', '--side', side, '--width', 1400, '--height',
            1500, '--quality', 'basic', '-o', OUT / f'{prefix}-{side}.png',
            board_file)
    if iso:
        run(CLI, 'pcb', 'render', '--perspective', '--rotate', '-35,0,30',
            '--width', 1600, '--height', 1200, '--quality', 'basic', '-o',
            OUT / f'{prefix}-iso.png', board_file)


if not args.only_2d:
    render3d(pcb, 'pcba', True)
    # Bare board: the same file with every 3D model removed, beside the
    # project so the footprint and model paths still resolve.
    bare_dir = pcb.parent / '.render-bare'
    shutil.rmtree(bare_dir, ignore_errors=True)
    bare_dir.mkdir()
    for f in pcb.parent.glob(pcb.stem + '.kicad_p*'):
        shutil.copy(f, bare_dir / f.name)
    bare = p.LoadBoard(str(bare_dir / pcb.name))
    for f in bare.GetFootprints():
        f.Models().clear()
    bare.Save(str(bare_dir / pcb.name))
    render3d(bare_dir / pcb.name, 'bare', False)
    shutil.rmtree(bare_dir)

# --- 2D views ---------------------------------------------------------------
try:
    FONT = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 14)
    SMALL = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 11)
except OSError:
    FONT = SMALL = ImageFont.load_default()
mm = p.ToMM
# View extent: the outline (Edge.Cuts, wherever an older board put its
# origin) plus whatever overhangs it (antenna, jack nozzle).
_edge = board.GetBoardEdgesBoundingBox()
EX0, EY0, EX1, EY1 = (mm(_edge.GetLeft()), mm(_edge.GetTop()),
                      mm(_edge.GetRight()), mm(_edge.GetBottom()))
_boxes = [f.GetBoundingBox(False) for f in board.GetFootprints()]
X0 = min([EX0] + [mm(b.GetLeft()) for b in _boxes]) - M
Y0 = min([EY0] + [mm(b.GetTop()) for b in _boxes]) - M
X1 = max([EX1] + [mm(b.GetRight()) for b in _boxes]) + M
Y1 = max([EY1] + [mm(b.GetBottom()) for b in _boxes]) + M


def canvas(title):
    im = Image.new('RGB', (int((X1 - X0) * S), int((Y1 - Y0) * S) + 30), 'white')
    d = ImageDraw.Draw(im)
    d.text((10, 6), title, fill='black', font=FONT)
    d.rectangle([px(EX0, EY0), px(EX1, EY1)], outline='black', width=2)
    return im, d


def px(x, y):
    return (int((x - X0) * S), int((y - Y0) * S) + 30)


def poly_points(chain):
    return [px(mm(chain.CPoint(i).x), mm(chain.CPoint(i).y))
            for i in range(chain.PointCount())]


def draw_zones(d, layer, fill):
    for z in board.Zones():
        if z.GetIsRuleArea() or not z.IsOnLayer(layer):
            continue
        polys = z.GetFilledPolysList(layer)
        for i in range(polys.OutlineCount()):
            pts = poly_points(polys.Outline(i))
            if len(pts) > 2:
                d.polygon(pts, fill=fill)
            for h in range(polys.HoleCount(i)):
                hp = poly_points(polys.Hole(i, h))
                if len(hp) > 2:
                    d.polygon(hp, fill='white')


def draw_pads(d, layer, tint=None):
    for f in board.GetFootprints():
        for a in f.Pads():
            if not a.IsOnLayer(layer):
                continue
            poly = a.GetEffectivePolygon(layer)
            for i in range(poly.OutlineCount()):
                pts = poly_points(poly.Outline(i))
                if len(pts) > 2:
                    d.polygon(pts, fill=tint or colour(a.GetNetname()))
            if a.GetDrillSizeX():
                c = px(mm(a.GetPosition().x), mm(a.GetPosition().y))
                r = mm(a.GetDrillSizeX()) / 2 * S
                d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill='white')


def draw_tracks(d, layer, tint=None):
    for t in board.GetTracks():
        if isinstance(t, p.PCB_VIA):
            c = px(mm(t.GetPosition().x), mm(t.GetPosition().y))
            r = mm(t.GetWidth(p.F_Cu)) / 2 * S
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r],
                      fill=tint or colour(t.GetNetname()), outline='black')
            continue
        if t.GetLayer() != layer:
            continue
        a, b = (px(mm(t.GetStart().x), mm(t.GetStart().y)),
                px(mm(t.GetEnd().x), mm(t.GetEnd().y)))
        w = max(1, int(mm(t.GetWidth()) * S))
        col = tint or colour(t.GetNetname())
        d.line([a, b], fill=col, width=w)
        for e in (a, b):
            d.ellipse([e[0] - w / 2, e[1] - w / 2, e[0] + w / 2, e[1] + w / 2], fill=col)


def legend(d, y0):
    x = 10
    for label, col, _ in GROUPS + [OTHER + (set(),)]:
        d.rectangle([x, y0, x + 14, y0 + 14], fill=col)
        d.text((x + 18, y0), label, fill='black', font=SMALL)
        x += 30 + int(d.textlength(label, font=SMALL))


LAYERS = [('F.Cu', p.F_Cu), ('In1.Cu', p.In1_Cu), ('In2.Cu', p.In2_Cu), ('B.Cu', p.B_Cu)]
for name, layer in LAYERS:
    im, d = canvas(f'{name} copper (top view)')
    draw_zones(d, layer, (205, 222, 240))
    draw_pads(d, layer)
    draw_tracks(d, layer)
    im.save(OUT / f'layer-{name.replace(".", "_")}.png')

# Routing map: F.Cu solid, B.Cu drawn lighter underneath, pads outlined.
im, d = canvas('Routing, outer layers: F.Cu bold, B.Cu faded (top view)')
for t in board.GetTracks():
    if not isinstance(t, p.PCB_VIA) and t.GetLayer() == p.B_Cu \
            and t.GetNetname() not in ('GND',):
        a, b = (px(mm(t.GetStart().x), mm(t.GetStart().y)),
                px(mm(t.GetEnd().x), mm(t.GetEnd().y)))
        c = colour(t.GetNetname())
        faded = tuple(int(v + (255 - v) * .6) for v in c)
        d.line([a, b], fill=faded, width=max(1, int(mm(t.GetWidth()) * S)))
draw_pads(d, p.F_Cu)
draw_tracks(d, p.F_Cu)
for f in board.GetFootprints():
    c = px(mm(f.GetPosition().x), mm(f.GetPosition().y))
    d.text(c, f.GetReference(), fill='black', font=SMALL, anchor='mm')
legend(d, im.height - 22)
im.save(OUT / 'routing.png')

# Assembly drawing: courtyards, refs, values, pin 1 and polarity.
im, d = canvas('Assembly, top side: reference / value; red dot = pin 1, '
               'K = cathode, + = tantalum plus')
top = [f for f in board.GetFootprints() if not f.IsFlipped()]
for f in top:
    if f.GetReference().startswith('H'):
        c = px(mm(f.GetPosition().x), mm(f.GetPosition().y))
        r = 1.1 * S
        d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline='black', width=2)
        d.text(c, f.GetReference(), fill='black', font=SMALL, anchor='mm')
        continue
    cy = f.GetCourtyard(p.F_CrtYd)
    for i in range(cy.OutlineCount()):
        pts = poly_points(cy.Outline(i))
        if len(pts) > 2:
            d.polygon(pts, outline=(120, 120, 120), fill=(246, 246, 246))
    draw_pads(d, p.F_Cu, tint=(200, 170, 90))
for f in top:
    if f.GetReference().startswith('H'):
        continue
    c = px(mm(f.GetPosition().x), mm(f.GetPosition().y))
    d.text((c[0], c[1] - 7), f.GetReference(), fill='black', font=FONT, anchor='mm')
    d.text((c[0], c[1] + 8), f.GetValue(), fill=(60, 60, 60), font=SMALL, anchor='mm')
    # Pin 1 on ICs / connectors; pad 1 of the polarised two-pins is the
    # cathode (LED D4, Schottky D5) or the plus (tantalum C25). D2 / D3 are
    # bidirectional.
    one = next((a for a in f.Pads() if a.GetNumber() in ('1', 'A1')), None)
    mark = {'D4': 'K', 'D5': 'K', 'C25': '+'}.get(f.GetReference())
    if one is not None and (len(f.Pads()) > 2 or mark):
        e = px(mm(one.GetPosition().x), mm(one.GetPosition().y))
        d.ellipse([e[0] - 5, e[1] - 5, e[0] + 5, e[1] + 5], fill=(220, 30, 30))
        if mark:
            d.text((e[0] + 8, e[1] - 8), mark, fill=(220, 30, 30), font=FONT)
im.save(OUT / 'assembly-top.png')
if not args.only_2d:
    run(CLI, 'pcb', 'export', 'pdf', '--layers', 'F.Fab,F.Courtyard,Edge.Cuts',
        '--mode-single', '-o', OUT / 'assembly-top.pdf', pcb)

# --- Differences against the previous run -----------------------------------
pairs = []
for f in sorted(OUT.glob('*.png')):
    old = PREV / f.name
    if not old.exists():
        continue
    a, b = Image.open(old).convert('RGB'), Image.open(f).convert('RGB')
    if a.size != b.size:
        b = b.resize(a.size)
    delta = ImageChops.difference(a, b).convert('L').point(lambda v: 255 if v > 24 else 0)
    box = delta.getbbox()
    if box is None:
        continue
    out = Image.blend(b, Image.new('RGB', b.size, 'white'), .55)
    out.paste((255, 0, 160), mask=delta)
    out.save(OUT / f'diff-{f.name}')
    pairs.append(f.name)

# --- Index ------------------------------------------------------------------
order = ['pcba-iso.png', 'pcba-top.png', 'pcba-bottom.png', 'bare-top.png',
         'bare-bottom.png', 'assembly-top.png', 'routing.png'] + \
        [f'layer-{n.replace(".", "_")}.png' for n, _ in LAYERS]
rows = []
for n in order:
    cells = [f'<figure><img src="{n}"><figcaption>{n} (now)</figcaption></figure>']
    if (PREV / n).exists():
        cells.insert(0, f'<figure><img src="../previous/{n}"><figcaption>{n} '
                        f'(previous)</figcaption></figure>')
    if n in pairs:
        cells.append(f'<figure><img src="diff-{n}"><figcaption>changed pixels '
                     f'in magenta</figcaption></figure>')
    rows.append(f'<section><h2>{html.escape(n)}</h2><div>{"".join(cells)}</div></section>')
STYLE = ('<style>body{font:14px system-ui;margin:16px;background:#fafafa}'
         'section div{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0;'
         'max-width:32%;min-width:240px}img{width:100%;border:1px solid #ccc;'
         'background:#fff}table{border-collapse:collapse;margin:8px 0 24px}'
         'td,th{border:1px solid #ccc;padding:4px 8px;vertical-align:top;'
         'text-align:left}.ver img{max-height:260px;width:auto;max-width:100%}'
         '.now{background:#eef6ee}</style>')


def history(here):
    """Version history from hardware/versions.json, links relative to here."""
    vers = json.loads((HW / 'versions.json').read_text())['versions']
    out = ['<h2 id="history">버전 기록</h2><table><tr><th>버전</th><th>날짜</th>'
           '<th>상태</th><th>요약</th><th>파일</th></tr>']
    for v in vers:
        rel = lambda f: os.path.relpath(HW / v['dir'] / f, here)
        files = ' · '.join(f'<a href="{rel(f)}">{html.escape(Path(f).name)}</a>'
                           for f in v.get('files', []))
        out.append(f'<tr class="{"now" if v["status"] == "current" else ""}">'
                   f'<td><b>{html.escape(v["name"])}</b><br>{html.escape(v["board"])}</td>'
                   f'<td>{v["date"]}</td><td>{html.escape(v["status_text"])}</td>'
                   f'<td>{html.escape(v["summary"])}</td><td>{files}</td></tr>')
    out.append('</table>')
    for v in reversed(vers):
        imgs = ''.join(
            f'<figure><img src="{os.path.relpath(HW / v["dir"] / i, here)}">'
            f'<figcaption>{html.escape(Path(i).name)}</figcaption></figure>'
            for i in v['images'] if (HW / v['dir'] / i).exists())
        out.append(f'<section class="ver"><h3>{html.escape(v["name"])} — '
                   f'{html.escape(v["board"])}</h3><div>{imgs}</div></section>')
    return ''.join(out)


(OUT / 'index.html').write_text(
    f'<!doctype html><meta charset="utf-8"><title>{html.escape(TITLE)}</title>{STYLE}'
    f'<h1>{html.escape(TITLE)}</h1><p><a href="#history">버전 기록</a></p>'
    + ''.join(rows) + (history(OUT) if CURRENT else ''))
if CURRENT:
    (HW / 'archive' / 'index.html').write_text(
        f'<!doctype html><meta charset="utf-8"><title>LOVELACE hardware versions</title>'
        f'{STYLE}<h1>LOVELACE 하드웨어 버전 기록</h1>' + history(HW / 'archive'))
print('Renders in', OUT, '| changed vs previous:',
      (pairs or 'none') if PREV.exists() else 'first run')
