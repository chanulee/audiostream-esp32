#!/usr/bin/env python3
"""Generate the KiCad board, schematic, BOM and CPL from design.json.

Run with KiCad's Python after plan_pcb.py. Hand-drawn here (before the
autorouter): buck SW node, inductor output, buck input loop, DAC analog
fan-out, USB-C D+/D- escape and one ground via per capacitor GND pad.
"""
import json, math, os, uuid, shutil, csv
from pathlib import Path
import pcbnew as p

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / 'lib'
KICAD_LIB = Path(os.environ.get(
    'KICAD_FOOTPRINT_DIR',
    '/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/footprints'))
data = json.loads((ROOT / 'design.json').read_text())
plan = json.loads((ROOT / 'placement.json').read_text())
W, H = plan['board']['w'], plan['board']['h']
NAME = 'lovelace-as-002'
# Stable IDs keep schematic and PCB references linked between regenerations.
uid = lambda s: str(uuid.uuid5(uuid.NAMESPACE_URL, 'lovelace-as-002-rev-b/' + s))
root_id = uid('root')
q = lambda s: json.dumps(str(s), ensure_ascii=False)
mm = p.FromMM
pt = lambda x, y: p.VECTOR2I(mm(x), mm(y))

board = p.BOARD()
board.SetCopperLayerCount(4)
rules = board.GetDesignSettings()
rules.m_MinClearance = mm(.15)
rules.m_TrackMinWidth = mm(.15)
rules.m_CopperEdgeClearance = mm(.4)
board.SetFileName(str(ROOT / f'{NAME}.kicad_pcb'))
nets = {n: p.NETINFO_ITEM(board, n)
        for n in sorted({n for d in data for n in d['nets'].values()})}
for n in nets.values():
    board.Add(n)

# Only footprints this design uses are shipped in lib/.
for old in LOCAL.glob('*.pretty'):
    if old.name != 'LOVELACE.pretty':
        shutil.rmtree(old)
footprints = {}
for d in data:
    lib, name = d['footprint'].split(':')
    src_dir = LOCAL if lib == 'LOVELACE' else KICAD_LIB
    f = p.FootprintLoad(str(src_dir / (lib + '.pretty')), name)
    assert f, d['footprint']
    if lib != 'LOVELACE':
        target = LOCAL / (lib + '.pretty')
        target.mkdir(exist_ok=True)
        shutil.copyfile(src_dir / (lib + '.pretty') / (name + '.kicad_mod'),
                        target / (name + '.kicad_mod'))
    f.SetFPID(p.LIB_ID(lib, name))
    f.SetReference(d['ref'])
    f.SetValue(d['value'])
    f.SetPath(p.KIID_PATH('/' + root_id + '/' + uid(d['ref'])))
    f.SetOrientationDegrees(d['rot'])
    f.SetPosition(pt(d['x'], d['y']))
    f.Value().SetVisible(False)
    if d['kind'] == 'mech':
        # Mounting holes live on the board only (no symbol, BOM or CPL line).
        f.SetBoardOnly(True)
        f.SetExcludedFromBOM(True)
        f.SetExcludedFromPosFiles(True)
    # Dense board: assembly references live on F.Fab, not on the silkscreen.
    f.Reference().SetLayer(p.F_Fab)
    f.Reference().SetTextSize(p.VECTOR2I(mm(.6), mm(.6)))
    f.Reference().SetTextThickness(mm(.1))
    for item in list(f.GraphicalItems()):
        if item.GetLayer() == p.Edge_Cuts:
            item.SetLayer(p.F_Fab)
        if item.GetLayer() == p.F_SilkS:
            bb = item.GetBoundingBox()
            if (p.ToMM(bb.GetLeft()) < .3 or p.ToMM(bb.GetRight()) > W - .3 or
                    p.ToMM(bb.GetTop()) < .3 or p.ToMM(bb.GetBottom()) > H - .3):
                f.Remove(item)
    for pad in f.Pads():
        num = pad.GetNumber()
        if num in d['nets']:
            pad.SetNet(nets[d['nets'][num]])
        elif num and (num in d['pin_names'] or d['ref'] == 'J1'):
            # Same name eeschema gives a no-connect pin, so parity stays clean.
            pin = d['pin_names'].get(num, num)
            nc = (f"unconnected-({d['ref']}-Pad{num})" if pin == num else
                  f"unconnected-({d['ref']}-{pin}-Pad{num})")
            if nc not in nets:
                nets[nc] = p.NETINFO_ITEM(board, nc)
                board.Add(nets[nc])
            pad.SetNet(nets[nc])
    board.Add(f)
    footprints[d['ref']] = f

for a, b in [((0, 0), (W, 0)), ((W, 0), (W, H)), ((W, H), (0, H)), ((0, H), (0, 0))]:
    s = p.PCB_SHAPE()
    s.SetShape(p.SHAPE_T_SEGMENT)
    s.SetStart(pt(*a))
    s.SetEnd(pt(*b))
    s.SetLayer(p.Edge_Cuts)
    s.SetWidth(mm(.05))
    board.Add(s)


def text(value, x, y, size=.8, layer=p.B_SilkS):
    t = p.PCB_TEXT(board)
    t.SetText(value)
    t.SetPosition(pt(x, y))
    t.SetTextSize(p.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(.15))
    t.SetLayer(layer)
    if layer == p.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


# All parts are on top, so user-facing labels go on the bottom silkscreen.
text('LOVELACE', 13, 16, 1.4)
text('AS-002  Wi-Fi + BT', 13, 19, .9)
text('USB-C 5V', 5.35, H - 2)
text('AUX', W - 8.0, H - 1.2)
sw1x, sw1y = [v / 1e6 for v in footprints['SW1'].GetPosition()]
text('BUTTON', sw1x, sw1y + 2.6)

# User artwork survives regeneration; only board-level silk is replaced.
from silkscreen import apply_saved
apply_saved(board, ROOT, W, H)


def track(a, b, net, width=.25, layer=p.F_Cu):
    t = p.PCB_TRACK(board)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(nets[net])
    board.Add(t)
    return t


def via(x, y, net, diam=.6, drill=.3):
    v = p.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(diam))
    v.SetDrill(mm(drill))
    v.SetLayerPair(p.F_Cu, p.B_Cu)
    v.SetViaType(p.VIATYPE_THROUGH)
    v.SetNet(nets[net])
    v.SetFrontTentingMode(p.TENTING_MODE_TENTED)
    v.SetBackTentingMode(p.TENTING_MODE_TENTED)
    board.Add(v)


def pad(ref, num):
    return next(a for a in footprints[ref].Pads() if a.GetNumber() == str(num))


def xy(item):
    return p.ToMM(item.GetPosition().x), p.ToMM(item.GetPosition().y)


def join45(a, b, net, width, layer=p.F_Cu):
    ax, ay = p.ToMM(a.x), p.ToMM(a.y)
    bx, by = p.ToMM(b.x), p.ToMM(b.y)
    dx, dy = bx - ax, by - ay
    if abs(dx) >= abs(dy):
        mid = pt(ax + math.copysign(abs(dy), dx), by)
    else:
        mid = pt(bx, ay + math.copysign(abs(dx), dy))
    if a != mid:
        track(a, mid, net, width, layer)
    if mid != b:
        track(mid, b, net, width, layer)


def path(points, net, width, layer=p.F_Cu):
    for a, b in zip(points, points[1:]):
        track(pt(*a), pt(*b), net, width, layer)


# --- Buck power stage (B2): SW on top copper only, short and wide ---------
sw_x, sw_y = xy(pad('U3', 7))
l1x, _ = xy(pad('L1', 1))
# Narrow neck past PG and the VOS sense via, then 0.6 mm to the inductor.
track(pt(sw_x, sw_y), pt(sw_x - 1.3, sw_y), 'SW', .25)
track(pt(sw_x - 1.3, sw_y), pt(l1x, sw_y), 'SW', .6)
# Input loop: VIN + EN to the C4 +5V pad, PGND straight to the C4 GND pad.
vin_x, vin_y = xy(pad('U3', 2))
en_x, en_y = xy(pad('U3', 3))
c4p, c4g = xy(pad('C4', 1)), xy(pad('C4', 2))
jx = vin_x + .75
track(pt(vin_x, vin_y), pt(jx, vin_y), '+5V', .3)
track(pt(en_x, en_y), pt(jx, en_y), '+5V', .25)
track(pt(jx, vin_y), pt(jx, en_y - .3), '+5V', .3)
join45(pt(jx, en_y - .3), pt(*c4p), '+5V', .3)
pg_x, pg_y = xy(pad('U3', 1))
join45(pt(pg_x, pg_y), pt(*c4g), 'GND', .3)

# --- USB-C: interleaved duplicate D+/D- pads escape inboard (B12) ---------
# A6/B6 (D+) join on top above the pad row; A7/B7 (D-) drop through vias
# and join on the bottom layer.
row_y = p.ToMM(pad('J1', 'A6').GetBoundingBox().GetTop())
for num in ('A6', 'B6'):
    x, _ = xy(pad('J1', num))
    track(pt(x, row_y + .2), pt(x, row_y - 1.1), 'USB_DP', .15)
xa, xb = xy(pad('J1', 'A6'))[0], xy(pad('J1', 'B6'))[0]
track(pt(xa, row_y - 1.1), pt(xb, row_y - 1.1), 'USB_DP', .15)
dm_vias = []
for num in ('A7', 'B7'):
    x, _ = xy(pad('J1', num))
    via(x, row_y - .4, 'USB_DM', .4, .2)
    track(pt(x, row_y + .2), pt(x, row_y - .4), 'USB_DM', .15)
    dm_vias.append(x)
track(pt(dm_vias[0], row_y - .4), pt(dm_vias[1], row_y - .4), 'USB_DM', .15,
      p.B_Cu)



# --- VBUS: one via above each VBUS pad, joined on B.Cu under the pad row --
va = (xy(pad('J1', 'A4'))[0], row_y - .88)
vb = (xy(pad('J1', 'A9'))[0] + .45, row_y - .68)
for v, padname in ((va, 'A4'), (vb, 'A9')):
    via(*v, 'VBUS')
    px_ = xy(pad('J1', padname))[0]
    knee_y = v[1] + abs(v[0] - px_)              # straight out of the pad row, then 45
    path([(px_, row_y + .2), (px_, knee_y), v], 'VBUS', .3)
under = row_y + 1.02
path([va, (va[0], under - 1.0), (va[0] + 1.0, under), (vb[0] - 1.0, under),
      (vb[0], under - 1.0), vb], 'VBUS', .4, p.B_Cu)
# --- USB D+/D- from the connector through the USBLC6 to the CH340N (B11) --
e1, e3, e4, e6 = (xy(pad('U5', n)) for n in (1, 3, 4, 6))
c1, c2 = xy(pad('U7', 1)), xy(pad('U7', 2))
xa = xy(pad('J1', 'A6'))[0]
# D+ climbs left of the USBLC6 to pin 1 and leaves pin 6 for UD+.
y_h = e3[1] + .95                         # below the pin-3 pad row
lane = e1[0] - 1.0                        # left of the pin column
path([(xa, row_y - 1.1), (xa, y_h + .4), (xa - .4, y_h), (lane + .4, y_h),
      (lane, y_h - .4), (lane, e1[1]), e1], 'USB_DP', .2)
path([e6, (c1[0], e6[1])], 'USB_DP', .2)
# D- hops on B.Cu to a via beside pin 4, then on B.Cu again to UD-.
dmx = max(dm_vias)
v_dm = (e4[0] + .41, e4[1] + 1.25)
path([(dmx, row_y - .4), (v_dm[0], row_y - .4 - (v_dm[0] - dmx)), v_dm], 'USB_DM', .2, p.B_Cu)
via(*v_dm, 'USB_DM', .4, .2)
path([v_dm, (v_dm[0], e4[1] + .41), e4], 'USB_DM', .2)
w_dm = (c2[0] - 1.49, c2[1])
path([v_dm, (w_dm[0] - (v_dm[1] - w_dm[1]), v_dm[1]), w_dm], 'USB_DM', .2, p.B_Cu)
via(*w_dm, 'USB_DM', .4, .2)
track(pt(*w_dm), pt(*c2), 'USB_DM', .2)

# --- USBLC6 flow-through: pins 1/6 (D+) and 3/4 (D-) are the same line ----
for x_, y_ in ((1, 6), (3, 4)):
    a_, b_ = xy(pad('U5', x_)), xy(pad('U5', y_))
    track(pt(*a_), pt(*b_), pad('U5', x_).GetNetname(), .2)

# --- USB-C side GND pads to the shell legs (B12) --------------------------
for gpad, side in (('A1', -1), ('A12', 1)):
    gx, _ = xy(pad('J1', gpad))
    sh = [xy(a) for a in footprints['J1'].Pads()
          if a.GetNumber() == 'SH' and (xy(a)[0] - xy(footprints['J1'])[0]) * side > 0]
    shx, shy = min(sh, key=lambda c: c[1])
    path([(gx, row_y + .8), (shx, row_y + .8)], 'GND', .3)

# --- Buck VOS senses the +3V3_D plane through its own via -----------------
vos = xy(pad('U3', 6))
vv = (vos[0] - 1.05, vos[1] - .35)
path([vos, (vos[0] - .7, vos[1]), vv], '+3V3_D', .2)
via(*vv, '+3V3_D', .6, .3)

# --- Module supply pins tie straight to their 100 nF (B1) -----------------
for upin, cpin in ((1, 2), (2, 1)):
    ux, uy = xy(pad('U1', upin))
    cx_, cy_ = xy(pad('C2', cpin))
    jog = abs(cy_ - uy)
    path([(cx_, cy_), (cx_ + jog, uy), (ux, uy)], pad('U1', upin).GetNetname(), .3)
g2 = xy(pad('C2', 2))
via(g2[0] - 1.2, g2[1], 'GND', .45, .2)
track(pt(*g2), pt(g2[0] - 1.2, g2[1]), 'GND', .3)

# --- DAC hold-up rail: C25 (top right) down the right edge to D5 ---------
# Drawn by hand so it neither crosses the module-to-DAC I2S run nor runs under
# the DAC; the router finishes D5 -> LDO.
cx_, cy_ = xy(pad('C25', 1))
kx, ky = xy(pad('D5', 1))
ex, top = W - .7, cy_ + 1.2        # edge lane; row just below the M2 keep-out
path([(cx_, cy_), (cx_, top), (ex - .4, top), (ex, top + .4), (ex, ky - .4),
      (ex - .4, ky), (kx, ky)], '+5V_DAC', .3)

# --- Plane fan-out: every SMD pad on GND / 3.3 V gets its own via (B8) -----
PLANES = ('GND', '+3V3_D')
u1x0, u1y0 = xy(footprints['U1'])
U1_BOTTOM = u1y0 + 15.0
# Rule areas created further down; vias must stay out of them.
NO_VIA = [(u1x0 - 9.81, 0, u1x0 + 9.81, .9),                      # antenna base
          (u1x0 - 7.7, 0, u1x0 + 7.7, U1_BOTTOM),                       # module body
          (0, 0, W, .4), (0, H - .4, W, H), (0, 0, .4, H), (W - .4, 0, W, H)]
allpads = [a for f in footprints.values() for a in f.Pads()]
holes = [(k['circle'][0], -k['circle'][1], k['circle'][2])
         for k in plan['keepouts'] if 'circle' in k]
placed = [(p.ToMM(t.GetPosition().x), p.ToMM(t.GetPosition().y))
          for t in board.GetTracks() if isinstance(t, p.PCB_VIA)]


def box_gap(b, x, y):
    return math.hypot(
        max(p.ToMM(b.GetLeft()) - x, 0, x - p.ToMM(b.GetRight())),
        max(p.ToMM(b.GetTop()) - y, 0, y - p.ToMM(b.GetBottom())))


def seg_gap(t, x, y):
    ax, ay = p.ToMM(t.GetStart().x), p.ToMM(t.GetStart().y)
    bx, by = p.ToMM(t.GetEnd().x), p.ToMM(t.GetEnd().y)
    dx, dy = bx - ax, by - ay
    k = 0 if dx == dy == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - k * dx, y - ay - k * dy)


tracked = [t for t in board.GetTracks() if not isinstance(t, p.PCB_VIA)]


def has_copper(a):
    """A hand-drawn track already starts on this pad."""
    b = a.GetBoundingBox()
    return any(t.GetNetname() == a.GetNetname() and
               (b.Contains(t.GetStart()) or b.Contains(t.GetEnd()))
               for t in tracked)


def fan_out(a):
    net = a.GetNetname()
    x, y = xy(a)
    # Prefer a standard 0.6/0.3 via; fall back to 0.45/0.2 in tight rows.
    for diam, drill, need in ((.6, .3, .5), (.45, .2, .38)):
        for offset in (.75, .95, 1.1, 1.25, 1.5, 1.75, 2.0):
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0),
                           (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7)):
                vx, vy = x + dx * offset, y + dy * offset
                edge = .45 + diam / 2
                if not (edge < vx < W - edge and edge < vy < H - edge):
                    continue
                if any(math.hypot(vx - hx, vy - hy) < r + .4 for hx, hy, r in holes):
                    continue
                if any(math.hypot(vx - ox, vy - oy) < diam + .2 for ox, oy in placed):
                    continue
                if any(math.hypot(max(x1 - sx, 0, sx - x2), max(y1 - sy, 0, sy - y2))
                       < tol
                       for x1, y1, x2, y2 in NO_VIA
                       for sx, sy, tol in [(x + (vx - x) * k / 6, y + (vy - y) * k / 6,
                                            diam / 2 + .1 if k == 6 else .2)
                                           for k in range(1, 7)]):
                    continue
                if any(t.GetNetname() != net and seg_gap(t, vx, vy) <
                       diam / 2 + p.ToMM(t.GetWidth()) / 2 + .2 for t in tracked):
                    continue
                if any(t.GetNetname() != net and min(
                        seg_gap(t, x + (vx - x) * k / 6, y + (vy - y) * k / 6)
                        for k in range(7)) < .15 + .15 + p.ToMM(t.GetWidth()) / 2
                       for t in tracked):
                    continue
                # Keep vias off the module, the USB shell and the jack body.
                if any(box_gap(footprints[r].GetBoundingBox(False), vx, vy) == 0
                       for r in ('U1', 'J1', 'J2')):
                    continue
                ok = True
                for other in allpads:
                    b = other.GetBoundingBox()
                    if box_gap(b, vx, vy) < need:
                        ok = False
                        break
                    # The 0.3 mm stub from the pad must also clear other nets.
                    if other.GetNetname() != net:
                        for k in range(1, 10):
                            sx, sy = x + (vx - x) * k / 10, y + (vy - y) * k / 10
                            if box_gap(b, sx, sy) < .3:
                                ok = False
                                break
                        if not ok:
                            break
                if not ok:
                    continue
                via(vx, vy, net, diam, drill)
                tracked.append(track(a.GetPosition(), pt(vx, vy), net, .3))
                placed.append((vx, vy))
                return True
    return False


def tie(a):
    """Join a plane pad to the nearest same-net via when a straight run is clear."""
    net, (x, y) = a.GetNetname(), xy(a)
    vias = sorted((t for t in board.GetTracks() if isinstance(t, p.PCB_VIA)
                   and t.GetNetname() == net), key=lambda t: math.hypot(xy(t)[0] - x, xy(t)[1] - y))
    for v in vias[:4]:
        vx, vy = xy(v)
        if math.hypot(vx - x, vy - y) > 3.0:
            break
        samples = [(x + (vx - x) * k / 10, y + (vy - y) * k / 10) for k in range(11)]
        if any(o.GetNetname() != net and min(box_gap(o.GetBoundingBox(), sx, sy) for sx, sy in samples) < .3
               for o in allpads):
            continue
        if any(t.GetNetname() != net and min(seg_gap(t, sx, sy) for sx, sy in samples)
               < .3 + p.ToMM(t.GetWidth()) / 2 for t in tracked):
            continue
        tracked.append(track(a.GetPosition(), v.GetPosition(), net, .25))
        return True
    return False


unfanned = []
for d in data:
    for a in footprints[d['ref']].Pads():
        if (a.GetNetname() not in PLANES or a.GetAttribute() != p.PAD_ATTRIB_SMD
                or not a.GetNumber()):
            continue
        # Hand-routed IC pins are done; capacitors / ESD still need their own
        # plane via (B8) unless one already sits on their stub.
        if has_copper(a) and (not d['ref'].startswith(('C', 'D')) or any(
                isinstance(t, p.PCB_VIA) and t.GetNetname() == a.GetNetname()
                and math.hypot(p.ToMM(t.GetPosition().x) - xy(a)[0],
                               p.ToMM(t.GetPosition().y) - xy(a)[1]) < 1.8
                for t in board.GetTracks())):
            continue
        # Thermal pads / module EP already carry their own vias.
        if (d['ref'], a.GetNumber()) in (('U1', '39'), ('U3', '9')):
            continue
        if not fan_out(a) and not tie(a):
            unfanned.append(f"{d['ref']}.{a.GetNumber()}")
            # No via of its own: a solid pour connection instead of one spoke.
            a.SetLocalZoneConnection(p.ZONE_CONNECTION_FULL)
# eFuse IN / OUT bars are reachable only at their ends, DVDT sits on the far
# side of the package: give the router a via at each.
for ref, num in (('U6', '5'), ('U6', '6'), ('U6', '7'), ('C22', '1'), ('C21', '1')):
    if not fan_out(pad(ref, num)):
        unfanned.append(f'{ref}.{num}')
# Supply / power capacitors and line ESD must each have their own via (B8).
# IC pins, the EN RC (C1) and the USBLC6 reference cap (C23, no load
# current) may reach the plane through the router.
OWN_VIA = ('C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C9', 'C10', 'C14', 'C15',
           'C16', 'C17', 'C18', 'C21', 'C24', 'D2', 'D3')
assert not [u for u in unfanned if u.split('.')[0] in OWN_VIA], unfanned
print('Plane pads left to the router:', unfanned)


# --- Rule areas -------------------------------------------------------------
def rule_area(points, layers=None, layer=None):
    z = p.ZONE(board)
    z.SetIsRuleArea(True)
    if layers is not None:
        z.SetLayerSet(layers)
    else:
        z.SetLayer(layer)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowZoneFills(True)
    z.Outline().NewOutline()
    for x, y in points:
        z.Outline().Append(mm(x), mm(y))
    board.Add(z)


def box(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# Screw heads: no copper on any layer.
for x, y, r in holes:
    rule_area([(x + r * math.cos(i * math.pi / 16), y + r * math.sin(i * math.pi / 16))
               for i in range(32)], p.LSET.AllCuMask())
# USB-C shell: only the pin row may carry top copper (B12).
jx, jy = xy(footprints['J1'])
rule_area(box(jx - 4.9, row_y + 1.6, jx + 4.9, H - .3), layer=p.F_Cu)
# No tracks or vias under the module body (its underside has the EP only).
u1x, u1y = xy(footprints['U1'])
rule_area(box(u1x - 7.7, .3, u1x + 7.7, u1y + 15.0), p.LSET.AllCuMask())
for z in list(board.Zones())[-1:]:
    z.SetDoNotAllowZoneFills(False)
# Antenna base: the module's top 1 mm sits at the board edge; keep pours off it.
rule_area(box(u1x - 9.81, .3, u1x + 9.81, .9), p.LSET.AllCuMask())
# Copper edge band reserved for the router as well as the DRC.
for b in [(0, 0, W, .4), (0, H - .4, W, H), (0, 0, .4, H), (W - .4, 0, W, H)]:
    rule_area(box(*b), p.LSET.AllCuMask())

# KiCad writes items in UUID order and the router takes nets in file order:
# stable UUIDs make the same design route the same way on every run.
for kind, items in (('fp', [footprints[d['ref']] for d in data]),
                    ('track', list(board.GetTracks())),
                    ('zone', list(board.Zones())),
                    ('drawing', list(board.GetDrawings()))):
    for i, item in enumerate(items):
        item.SetUuidDirect(p.KIID(uid(f'{kind}/{i}')))
p.SaveBoard(str(ROOT / f'{NAME}.kicad_pcb'), board)

# --- Schematic: self-contained symbols with physical pin numbers ----------
libdefs, instances, labels, ncs = [], [], [], []
major = [d for d in data if d['ref'] in ['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7', 'J1', 'J2']]
minor = [d for d in data if d not in major and d['kind'] != 'mech']
locs = {'U1': (65, 85), 'U2': (195, 75), 'U3': (310, 40), 'U4': (400, 40),
        'U5': (310, 90), 'J1': (400, 110), 'J2': (505, 40), 'U6': (505, 130),
        'U7': (400, 155)}
for i, d in enumerate(minor):
    locs[d['ref']] = (55 + (i % 7) * 75, 200 + (i // 7) * 26)
PIN_TYPES = {
    'U3': {'1': 'power_in', '2': 'power_in', '3': 'input', '4': 'power_in',
           '5': 'input', '6': 'input', '7': 'power_out', '8': 'open_collector',
           '9': 'power_in'},
    'U6': {'1': 'input', '2': 'input', '3': 'open_collector', '4': 'open_collector',
           '5': 'power_in', '6': 'power_out', '7': 'passive', '8': 'power_in',
           '9': 'passive', '10': 'passive'},
    'U4': {'1': 'power_in', '2': 'power_in', '3': 'input', '4': 'no_connect',
           '5': 'power_out'},
    # The hold-up diode is the only source of the DAC's +5V_DAC rail.
    'D5': {'1': 'power_out', '2': 'power_in'},
}
for d in major + minor:
    ref = d['ref']
    sym = 'AudioStream:' + ref
    x, y = [round(v / 1.27) * 1.27 for v in locs[ref]]
    pins = list(d['pin_names']) if d['pin_names'] else list(d['nets'])
    if ref == 'J1':
        pins += ['A8', 'B8']
    rows = math.ceil(len(pins) / 2)
    height = max(5.08, (rows + 1) * 1.27)
    pin_items = []
    for i, num in enumerate(pins):
        left = i < rows
        row = i if left else i - rows
        px = -15.24 if left else 15.24
        py = height - 2.54 * (row + 1)
        name = d['pin_names'].get(num, num)
        net = d['nets'].get(num)
        typ = PIN_TYPES.get(ref, {}).get(num, 'passive')
        if ref == 'U1':
            typ = ('power_in' if num in ['1', '2', '15', '38', '39'] else
                   'output' if num in ['30', '31', '35', '36', '37'] else 'bidirectional')
        if ref == 'U2':
            typ = ('power_in' if num in ['1', '3', '8', '9', '19', '20'] else
                   'output' if num in ['5', '6', '7', '18'] else
                   'input' if num in ['10', '11', '12', '13', '14', '15', '16', '17']
                   else 'passive')
        pin_items.append(
            f'(pin {typ} line (at {px} {py:.3f} {0 if left else 180}) (length 5.08) '
            f'(name {q(name)} (effects (font (size 1 1)))) '
            f'(number {q(num)} (effects (font (size 1 1)))))')
        ax, ay = x + px, y - py
        ex = ax + (-7.62 if left else 7.62)
        if net:
            labels.append(f'(wire (pts (xy {ax:.3f} {ay:.3f}) (xy {ex:.3f} {ay:.3f})) '
                          f'(stroke (width 0) (type default)) (uuid {q(uid(ref + num + "wire"))}))')
            # Global labels keep board net names ("EN", not "/EN").
            labels.append(f'(global_label {q(net)} (shape passive) (at {ex:.3f} {ay:.3f} {180 if left else 0}) '
                          f'(effects (font (size 1 1)) (justify {"right" if left else "left"})) '
                          f'(uuid {q(uid(ref + num + "label"))}))')
        else:
            ncs.append(f'(no_connect (at {ax:.3f} {ay:.3f}) (uuid {q(uid(ref + num + "nc"))}))')
    libdefs.append(f'''(symbol {q(sym)} (pin_names (offset 0.5)) (in_bom yes) (on_board yes)
 (property "Reference" {q(ref.rstrip('0123456789'))} (at 0 {height + 3:.3f} 0) (effects (font (size 1.27 1.27))))
 (property "Value" {q(d['value'])} (at 0 {-height - 3:.3f} 0) (effects (font (size 1 1))))
 (property "Footprint" {q(d['footprint'])} (at 0 0 0) (effects (font (size 1 1)) hide))
 (symbol {q(ref + '_0_1')} (rectangle (start -10.16 {height:.3f}) (end 10.16 {-height:.3f}) (stroke (width .254) (type default)) (fill (type background))))
 (symbol {q(ref + '_1_1')} {''.join(pin_items)}))''')
    instances.append(f'''(symbol (lib_id {q(sym)}) (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {q(uid(ref))})
 (property "Reference" {q(ref)} (at {x} {y - height - 3:.3f} 0) (effects (font (size 1.27 1.27))))
 (property "Value" {q(d['value'])} (at {x} {y + height + 3:.3f} 0) (effects (font (size 1 1))))
 (property "Footprint" {q(d['footprint'])} (at {x} {y} 0) (effects (font (size 1 1)) hide))
 {''.join('(pin ' + q(n) + ' (uuid ' + q(uid(ref + n + 'pin')) + '))' for n in pins)}
 (instances (project {q(NAME)} (path {q('/' + root_id)} (reference {q(ref)}) (unit 1)))))''')
# Power flags document USB power and the common ground for ERC.
for i, net in enumerate(['VBUS', 'GND', '+3V3_D']):
    name = 'Flag' + str(i)
    sym = 'AudioStream:' + name
    x, y = round((300 + i * 40) / 1.27) * 1.27, round(155 / 1.27) * 1.27
    libdefs.append(f'(symbol {q(sym)} (in_bom no) (on_board no) (property "Reference" "#FLG" (at 0 3 0) (effects (font (size 1 1)) hide)) (property "Value" "PWR_FLAG" (at 0 5 0) (effects (font (size 1 1)))) (symbol {q(name + "_1_1")} (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))')
    instances.append(f'(symbol (lib_id {q(sym)}) (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (uuid {q(uid(name))}) (property "Reference" {q("#FLG0" + str(i))} (at {x} {y} 0) (effects (font (size 1 1)) hide)) (property "Value" "PWR_FLAG" (at {x} {y - 3} 0) (effects (font (size 1 1)))) (pin "1" (uuid {q(uid(name + "pin"))})) (instances (project {q(NAME)} (path {q("/" + root_id)} (reference {q("#FLG0" + str(i))}) (unit 1)))))')
    labels.append(f'(global_label {q(net)} (shape passive) (at {x} {y} 0) (effects (font (size 1 1)) (justify left)) (uuid {q(uid(name + "label"))}))')
schematic = f'''(kicad_sch (version 20250114) (generator "eeschema") (uuid {q(root_id)}) (paper "A2")
 (title_block (title "LOVELACE / AS-002") (rev "B") (comment 1 "USB-C 5V; OVP eFuse + POWER switch; WROVER-E N8R8; PCM5102A; Wi-Fi + Classic BT; USB UART"))
 (lib_symbols {''.join(libdefs)}) {''.join(instances)} {''.join(labels)} {''.join(ncs)}
 (sheet_instances (path "/" (page "1"))))'''
(ROOT / f'{NAME}.kicad_sch').write_text(schematic)
(ROOT / 'AudioStream.kicad_sym').write_text(
    '(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor") '
    + ''.join(libdefs).replace('AudioStream:', '') + ')')
(ROOT / 'sym-lib-table').write_text(
    '(sym_lib_table (version 7) (lib (name "AudioStream") (type "KiCad") '
    '(uri "${KIPRJMOD}/AudioStream.kicad_sym") (options "") '
    '(descr "Project symbols, physical pin numbers")))\n')
project = {
    'board': {'design_settings': {
        'rules': {'min_clearance': .15, 'min_track_width': .15,
                  'min_via_diameter': .4, 'min_through_hole_diameter': .2,
                  'min_copper_edge_clearance': .4},
        'defaults': {'track_width': .2},
        # Copies are trimmed (edge silk, reference on F.Fab) on purpose.
        'rule_severities': {'lib_footprint_mismatch': 'ignore',
                            'lib_footprint_issues': 'ignore'}}},
    # Power: 0.77 A (ILIM + 15 %) needs 0.26 mm on 1 oz outer copper at
    # +10 C (reports/power-calcs.txt); 0.3 mm still fits the USB-C pad row.
    'net_settings': {
        'classes': [
            {'name': 'Default', 'clearance': .15, 'track_width': .2,
             'via_diameter': .6, 'via_drill': .3, 'diff_pair_width': .2,
             'diff_pair_gap': .15, 'diff_pair_via_gap': .25},
            {'name': 'Power', 'clearance': .2, 'track_width': .3,
             'via_diameter': .6, 'via_drill': .3},
            {'name': 'USB', 'clearance': .15, 'track_width': .2,
             'via_diameter': .4, 'via_drill': .2, 'diff_pair_width': .2,
             'diff_pair_gap': .15}],
        'netclass_patterns': [
            *[{'netclass': 'Power', 'pattern': n}
              for n in ('VBUS', '+5V', '+5V_DAC', '+3V3_D', '+3V3_A', 'SW')],
            {'netclass': 'USB', 'pattern': 'USB_D*'}]},
    'meta': {'filename': f'{NAME}.kicad_pro', 'version': 1}}
(ROOT / f'{NAME}.kicad_pro').write_text(json.dumps(project, indent=2))
# Reload so the project's net classes reach the router. It only sees the outer
# layers; L2 = GND and L3 = power planes.
routed = p.LoadBoard(str(ROOT / f'{NAME}.kicad_pcb'))
# L2 / L3 go to the router as power planes (GND, +3V3_D), so it drops plane
# vias for them instead of routing traces. +3V3_A (~30 mA) is routed.
for layer in (p.In1_Cu, p.In2_Cu):
    routed.SetLayerType(layer, p.LT_POWER)
for net, layer, (x1, y1, x2, y2), prio in [
        ('GND', p.In1_Cu, (.4, .4, W - .4, H - .4), 0),
        ('+3V3_D', p.In2_Cu, (.4, .4, W - .4, H - .4), 0)]:
    z = p.ZONE(routed)
    z.SetLayer(layer)
    z.SetNet(routed.FindNet(net))
    z.SetAssignedPriority(prio)
    z.Outline().NewOutline()
    for zx, zy in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
        z.Outline().Append(mm(zx), mm(zy))
    routed.Add(z)
p.ZONE_FILLER(routed).Fill(routed.Zones())
dsn = ROOT / f'{NAME}.dsn'
assert p.ExportSpecctraDSN(routed, str(dsn))
# Scripted export drops project net classes; write the power class directly.
POWER = ['VBUS', '+5V', '+5V_DAC', '+3V3_D', '+3V3_A', 'SW']
text_dsn = dsn.read_text()
start = text_dsn.index('    (class kicad_default ')
end = text_dsn.index('(circuit', start)
members = [n for n in text_dsn[start + len('    (class kicad_default '):end].split()
           if n not in POWER]
via_rule = text_dsn[end:text_dsn.index('(rule', end)]
cls = ('    (class kicad_default ' + ' '.join(members) + '\n      ' + via_rule +
       '(rule\n        (width 200)\n        (clearance 160)\n      )\n    )\n'
       '    (class Power ' + ' '.join(POWER) + '\n      ' + via_rule +
       '(rule\n        (width 300)\n        (clearance 200)\n      )\n    )\n')
close = text_dsn.index('\n    )\n', text_dsn.index('(rule', end)) + len('\n    )\n')
text_dsn = text_dsn[:start] + cls + text_dsn[close:]
# Router clearance 0.16 mm keeps its rounding above the 0.15 mm DRC rule.
text_dsn = text_dsn.replace('    (rule\n      (width 200)\n      (clearance 200)',
                            '    (rule\n      (width 200)\n      (clearance 160)', 1)
dsn.write_text(text_dsn)
libs = sorted({d['footprint'].split(':')[0] for d in data})
(ROOT / 'fp-lib-table').write_text(
    '(fp_lib_table (version 7)\n' + ''.join(
        f'(lib (name {q(l)}) (type "KiCad") (uri "${{KIPRJMOD}}/lib/{l}.pretty") '
        f'(options "") (descr "Project copy"))\n' for l in libs) + ')\n')
# JLCPCB upload format: one line per LCSC part, designators grouped.
groups = {}
for d in data:
    if d['kind'] != 'mech':
        groups.setdefault((d['lcsc'], d['value'], d['footprint']), []).append(d['ref'])
with (ROOT / 'bom.csv').open('w') as out:
    w = csv.writer(out)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'Quantity'])
    for (lcsc, value, fp), refs in sorted(groups.items(), key=lambda g: g[1][0]):
        w.writerow([value, ','.join(refs), fp.split(':')[1], lcsc, len(refs)])
with (ROOT / 'cpl.csv').open('w') as out:
    w = csv.writer(out)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for d in data:
        if d['kind'] != 'mech':
            w.writerow([d['ref'], d['x'], -d['y'], 'Top', d['rot']])
print('Created board, schematic, BOM, CPL and DSN', f'{W} x {H} mm')
