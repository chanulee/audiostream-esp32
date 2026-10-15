#!/usr/bin/env python3
"""Simulated-annealing placement with the pcb-layout-skill checker rules as cost.

Run with KiCad's Python after plan_pcb.py:
    autoplace.py W H [iterations] [seed]
Reads design.json + placement.json (rules), writes positions.json
({ref: [x, y, rot]}, KiCad coordinates) which plan_pcb.py applies.
U1, J1 and J2 stay where plan_pcb.py puts them. Exit code 1 when hard
rules (spacing, edges, keep-outs, near / apart) are still violated.
"""
import json, math, random, sys
from pathlib import Path
import pcbnew as pcb

ROOT = Path(__file__).resolve().parent
W, H = float(sys.argv[1]), float(sys.argv[2])
ITER = int(sys.argv[3]) if len(sys.argv) > 3 else 120000
random.seed(int(sys.argv[4]) if len(sys.argv) > 4 else 1)
design = json.loads((ROOT / 'design.json').read_text())
rules = json.loads((ROOT / 'placement.json').read_text())
KICAD = Path('/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/footprints')
# Large parts are floorplanned by hand in plan_pcb.py; passives are annealed.
FIXED = {'U1', 'J1', 'J2', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7', 'L1', 'SW1', 'D2', 'D3',
         'C8', 'C9', 'C10', 'C12', 'C13', 'C14', 'C15', 'C16', 'C17', 'C18', 'R10',
         'C1', 'C2', 'C3', 'R5', 'C23', 'D5', 'C25'}
EDGE = .5
SPACING = {
    'passive-passive': .3, 'passive-power': .5, 'passive-ic': .35,
    'passive-module': .5, 'passive-connector': .5, 'power-power': 1.0,
    'power-ic': 1.0, 'power-module': 1.0, 'power-connector': 1.0,
    'ic-ic': 1.0, 'ic-module': 1.0, 'ic-connector': 1.0,
    'module-connector': 1.0, 'connector-connector': 1.0,
}
HOLE_R = 2.75
HW = [1.0]   # hard-rule weight, ramped up so the final placement is legal
# Nets on planes need vias, not wires; decoupling is scored per pin instead.
PLANE = {'GND', '+3V3_D', '+3V3_A'}
NET_WEIGHT = {'SW': 6, '+5V': 2, 'VBUS': 2, 'USB_DP': 3, 'USB_DM': 3,
              'DAC_L': 2, 'DAC_R': 2, 'LINE_L': 2, 'LINE_R': 2}
PIN_PAIRS = [  # (cap, pad, ic, pin, weight): supply pad next to its pin
    ('C1', '1', 'U1', '3', 8), ('C2', '1', 'U1', '2', 30), ('C3', '1', 'U1', '2', 4),
    ('C10', '1', 'U2', '1', 30), ('C14', '1', 'U2', '8', 30), ('C16', '1', 'U2', '20', 30),
    ('C18', '1', 'U2', '18', 30), ('C12', '1', 'U2', '2', 8), ('C12', '2', 'U2', '4', 8),
    ('C13', '1', 'U2', '5', 20), ('C9', '1', 'U2', '1', 4), ('C15', '1', 'U2', '8', 4),
    ('C17', '1', 'U2', '20', 4), ('C4', '1', 'U3', '2', 30), ('C4', '2', 'U3', '1', 20),
    ('C8', '1', 'U4', '1', 10), ('C9', '1', 'U4', '5', 10), ('C21', '1', 'U6', '5', 20),
    ('C23', '1', 'U5', '5', 6), ('C24', '1', 'U7', '5', 20), ('L1', '1', 'U3', '7', 30),
    ('C6', '1', 'L1', '2', 15), ('R6', '2', 'U1', '25', 2), ('R5', '2', 'U1', '3', 4),
    ('R13', '2', 'U6', '2', 10), ('R14', '1', 'U6', '2', 10), ('R16', '2', 'U6', '1', 10),
    ('R17', '1', 'U6', '1', 10), ('R15', '1', 'U6', '9', 10), ('C22', '1', 'U6', '7', 10),
    ('R10', '2', 'U2', '17', 4), ('R1', '1', 'J1', 'A5', 4), ('R2', '1', 'J1', 'B5', 4),
    ('R18', '2', 'D4', '2', 4), ('R11', '1', 'U2', '6', 1), ('R12', '1', 'U2', '7', 1),
]


def load(fp):
    lib, name = fp.split(':')
    base = ROOT / 'lib' if lib == 'LOVELACE' else KICAD
    return pcb.FootprintLoad(str(base / (lib + '.pretty')), name)


parts = {}
for d in design:
    f = load(d['footprint'])
    pads = {}
    for a in f.Pads():
        if a.GetNumber():
            pads.setdefault(a.GetNumber(), (pcb.ToMM(a.GetPosition().x), pcb.ToMM(a.GetPosition().y)))
    box = d['local_courtyard']
    if d['kind'] == 'mech':
        box = [-HOLE_R, -HOLE_R, HOLE_R, HOLE_R]
    parts[d['ref']] = dict(x=d['x'], y=d['y'], rot=d['rot'], box=box, pads=pads,
                           kind=d['kind'], nets=d['nets'])
# Edge parts follow the board size.
parts['J1']['y'] = H - 3.65
parts['J2']['x'], parts['J2']['y'] = W - 5.0, H - 6.22
refs = list(parts)
movable = [r for r in refs if r not in FIXED]


def rot_pt(p, lx, ly, rot=None):
    a = math.radians(p['rot'] if rot is None else rot)
    c, s = round(math.cos(a)), round(math.sin(a))
    return p['x'] + lx * c + ly * s, p['y'] - lx * s + ly * c


def rect(p):
    b = p['box']
    xs, ys = zip(*[rot_pt(p, x, y) for x in (b[0], b[2]) for y in (b[1], b[3])])
    return min(xs), min(ys), max(xs), max(ys)


def gap(a, b):
    return math.hypot(max(b[0] - a[2], a[0] - b[2], 0), max(b[1] - a[3], a[1] - b[3], 0))


def depth(a, b):
    ox, oy = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return min(ox, oy) if ox > 0 and oy > 0 else 0.0


def spacing(ka, kb):
    if 'mech' in (ka, kb):
        return 0.0
    return SPACING.get(f'{ka}-{kb}', SPACING.get(f'{kb}-{ka}', 0.3))


nets = {}
for r, p in parts.items():
    for pad, n in p['nets'].items():
        if n not in PLANE and pad in p['pads']:
            nets.setdefault(n, []).append((r, pad))
nets = {n: m for n, m in nets.items() if len({r for r, _ in m}) > 1}
part_nets = {r: [n for n, m in nets.items() if any(x == r for x, _ in m)] for r in refs}
near = [(n['a'], n['b'], n['max']) for n in rules['near']]
apart = [(n['a'], n['b'], n['min']) for n in rules['apart']]
pairs_of = {r: [pp for pp in PIN_PAIRS if r in (pp[0], pp[2])] for r in refs}
rules_of = {r: [x for x in near + apart if r in x[:2]] for r in refs}
rects = {r: rect(parts[r]) for r in refs}


def pad_pos(r, pad):
    lx, ly = parts[r]['pads'][pad]
    return rot_pt(parts[r], lx, ly)


def pair_pen(a, b):
    ra, rb = rects[a], rects[b]
    d = depth(ra, rb)
    need = spacing(parts[a]['kind'], parts[b]['kind'])
    g = gap(ra, rb)
    return HW[0] * (400 * d + (200 * (need - g) if g < need else 0.0))


# Rect keep-outs from placement.json (y up there, y down here).
KEEP = [((k['rect'][0], -k['rect'][3], k['rect'][2], -k['rect'][1]), set(k.get('allow', [])))
        for k in rules['keepouts'] if 'rect' in k]


def own_pen(r):
    x1, y1, x2, y2 = rects[r]
    pen = 0.0
    for box, allow in KEEP:
        if r not in allow:
            pen += 400 * depth(rects[r], box) + (100 if depth(rects[r], box) > 0 else 0)
    if r not in FIXED:
        e = 0.3 if parts[r]['kind'] == 'mech' else EDGE
        for m in (x1 - e, y1 - e, W - e - x2, H - e - y2):
            if m < 0:
                pen += 400 * -m
    for a, b, lim in rules_of[r]:
        g = gap(rects[a], rects[b])
        if (a, b, lim) in near:
            pen += 60 * max(0, g - lim)
        else:
            pen += 60 * max(0, lim - g)
    return HW[0] * pen


def wire(r):
    cost = 0.0
    for c, cp, ic, ip, w in pairs_of[r]:
        (x1, y1), (x2, y2) = pad_pos(c, cp), pad_pos(ic, ip)
        cost += w * (abs(x1 - x2) + abs(y1 - y2))
    return cost


def net_len(n):
    pts = [pad_pos(r, p) for r, p in nets[n]]
    xs, ys = zip(*pts)
    return NET_WEIGHT.get(n, 1) * (max(xs) - min(xs) + max(ys) - min(ys))


def local_cost(r):
    """Every term that changes when r moves (pair terms counted once per pair)."""
    c = own_pen(r) + wire(r) + sum(net_len(n) for n in part_nets[r])
    c += sum(pair_pen(r, o) for o in refs if o != r)
    return c


def total_cost():
    c = sum(pair_pen(a, b) for i, a in enumerate(refs) for b in refs[i + 1:])
    c += sum(own_pen(r) for r in refs)
    c += sum(wire(r) for r in refs) / 2
    c += sum(net_len(n) for n in nets)
    return c


T0, T1 = 30.0, 0.02
cur = total_cost()
best, best_state = cur, {r: (parts[r]['x'], parts[r]['y'], parts[r]['rot']) for r in refs}
for it in range(ITER):
    t = T0 * (T1 / T0) ** (it / ITER)
    if it % 5000 == 0:
        HW[0] = 1 + 19 * it / ITER
        cur = best = total_cost()
        best_state = {k: (parts[k]['x'], parts[k]['y'], parts[k]['rot']) for k in refs}
    r = random.choice(movable)
    p = parts[r]
    old = (p['x'], p['y'], p['rot'])
    before = local_cost(r)
    mv = random.random()
    if mv < .12 and p['kind'] != 'mech':
        p['rot'] = (p['rot'] + random.choice((90, 180, 270))) % 360
    elif mv < .15:
        # Long jump: lets a large part leave a pocket the wires pulled it into.
        p['x'] = round(random.uniform(1, W - 1) / .05) * .05
        p['y'] = round(random.uniform(1, H - 1) / .05) * .05
    else:
        step = max(.05, min(W, H) * .25 * t / T0 + .1)
        p['x'] = round((p['x'] + random.gauss(0, step)) / .05) * .05
        p['y'] = round((p['y'] + random.gauss(0, step)) / .05) * .05
    rects[r] = rect(p)
    delta = local_cost(r) - before
    if delta <= 0 or random.random() < math.exp(-delta / t):
        cur += delta
        if cur < best:
            best = cur
            best_state = {k: (parts[k]['x'], parts[k]['y'], parts[k]['rot']) for k in refs}
    else:
        p['x'], p['y'], p['rot'] = old
        rects[r] = rect(p)
for k, (x, y, rr) in best_state.items():
    parts[k]['x'], parts[k]['y'], parts[k]['rot'] = x, y, rr
    rects[k] = rect(parts[k])
# Greedy legalisation: hard rules dominate, small moves only.
HW[0] = 1000.0
for it in range(ITER // 5):
    r = random.choice(movable)
    p = parts[r]
    old = (p['x'], p['y'], p['rot'])
    before = local_cost(r)
    p['x'] = round((p['x'] + random.gauss(0, .15)) / .05) * .05
    p['y'] = round((p['y'] + random.gauss(0, .15)) / .05) * .05
    rects[r] = rect(p)
    if local_cost(r) > before:
        p['x'], p['y'], p['rot'] = old
        rects[r] = rect(p)
best_state = {k: (parts[k]['x'], parts[k]['y'], parts[k]['rot']) for k in refs}
HW[0] = 1.0
violation = sum(pair_pen(a, b) for i, a in enumerate(refs) for b in refs[i + 1:])
violation += sum(own_pen(r) for r in refs)
(ROOT / 'positions.json').write_text(json.dumps(
    {'board': [W, H], 'parts': {k: [round(v[0], 3), round(v[1], 3), v[2]] for k, v in best_state.items()}},
    indent=1) + '\n')
print(f'{W} x {H}: cost {best:.1f}, hard-rule penalty {violation:.2f}')
if violation > 1e-6:
    worst = sorted(((pair_pen(a, b), a, b) for i, a in enumerate(refs) for b in refs[i + 1:]),
                   reverse=True)[:6] + sorted(((own_pen(r), r, '-') for r in refs), reverse=True)[:6]
    print('  worst:', [(round(v, 1), a, b) for v, a, b in worst if v > 0])
sys.exit(0 if violation < 1e-6 else 1)
