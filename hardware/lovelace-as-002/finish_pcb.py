#!/usr/bin/env python3
"""Import outer-layer routing (FreeRouting .ses with --ses) and pour the planes.

L1 parts + signals, L2 solid GND, L3 +3V3_D, L4 signals + GND. The analog
+3V3_A rail (LDO -> DAC, ~30 mA) is routed as traces. Run with KiCad's Python.
"""
import json, math, sys
from pathlib import Path
import pcbnew as p

ROOT = Path(__file__).resolve().parent
NAME = 'lovelace-as-002'
plan = json.loads((ROOT / 'placement.json').read_text())
W, H = plan['board']['w'], plan['board']['h']
board = p.LoadBoard(str(ROOT / f'{NAME}.kicad_pcb'))
# KiCadRoutingTools writes its tracks into the board itself; FreeRouting
# returns a session file.
if '--ses' in sys.argv:
    ses = ROOT / f'{NAME}.ses'
    assert p.ImportSpecctraSES(board, str(ses))
    print('Imported', ses.name)
# Vias the router did not use as vias (non-plane nets), judged by KiCad's own
# connectivity: kept when connected on two layers. On one layer, two or more
# tracks that meet only through the via pad are joined at its centre first; a
# lone escape stub left dangling by the removal goes with the via.
PLANE_NETS = ('GND', '+3V3_D')
board.BuildConnectivity()
conn = board.GetConnectivity()
for v in [t for t in board.GetTracks() if isinstance(t, p.PCB_VIA)]:
    if v.GetNetname() in PLANE_NETS:
        continue
    on = [lay for lay in (p.F_Cu, p.B_Cu) if conn.IsConnectedOnLayer(v, lay)]
    if len(on) >= 2:
        continue
    pos = v.GetPosition()
    touching = list(conn.GetConnectedTracks(v))
    if len(touching) >= 2:
        for t in touching:
            end = min((t.GetStart(), t.GetEnd()),
                      key=lambda e: (e - pos).EuclideanNorm())
            if end != pos:
                s = p.PCB_TRACK(board)
                s.SetStart(end)
                s.SetEnd(pos)
                s.SetLayer(t.GetLayer())
                s.SetWidth(min(a.GetWidth() for a in touching))
                s.SetNet(t.GetNet())
                board.Add(s)
    board.Delete(v)
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    if len(touching) == 1 and conn.TestTrackEndpointDangling(touching[0], False):
        board.Delete(touching[0])
        board.BuildConnectivity()
        conn = board.GetConnectivity()
# KiCadRoutingTools leaves a few sub-0.1 mm slivers that end in nothing;
# removing them changes no connection.
slivers = [t for t in board.GetTracks() if not isinstance(t, p.PCB_VIA)
           and t.GetLength() < p.FromMM(.1)
           and conn.TestTrackEndpointDangling(t, False)]
for t in slivers:
    board.Delete(t)
print('Removed dangling slivers:', len(slivers))
assert not any(t.GetLayer() in (p.In1_Cu, p.In2_Cu) and not isinstance(t, p.PCB_VIA)
               for t in board.GetTracks()), 'signal track on a plane layer'

# --- Bring-up test pads on the empty bottom side ----------------------------
# A 1.0 mm pad on B.Cu over one of the net's vias, or over a new via with a
# short F.Cu stub from one of its pads. No routing changes; board-only parts,
# so no BOM / CPL line. Label = footprint reference on B.Silkscreen.
TP_NETS = [  # (label, net, part whose pads the pad should sit near)
    ('VBUS', 'VBUS', 'J1'), ('5V', '+5V', 'U6'), ('5VD', '+5V_DAC', 'D5'),
    ('3V3', '+3V3_D', 'U3'), ('3V3A', '+3V3_A', 'U4'), ('GND', 'GND', 'L1'),
    ('GND2', 'GND', 'U2'), ('TX', 'UART_TX', 'U7'), ('RX', 'UART_RX', 'U7'),
    ('EN', 'EN', 'C1'), ('IO0', 'BOOT', 'SW1'), ('MUTE', 'XSMT', 'U1')]
TP_R, GAP = p.FromMM(.5), p.FromMM(.25)
tp_lib = p.FootprintLoad(str(Path('/Volumes/KiCad/KiCad/KiCad.app/Contents/'
                                  'SharedSupport/footprints/TestPoint.pretty')),
                         'TestPoint_Pad_D1.0mm')
fps = {f.GetReference(): f for f in board.GetFootprints()}
edge = p.FromMM(.4) + TP_R


def free_on(layer, pos, radius, net, skip=()):
    """No copper of another net on layer within radius + GAP of pos."""
    if not (edge <= pos.x <= p.FromMM(W) - edge and edge <= pos.y <= p.FromMM(H) - edge):
        return False
    for t in board.GetTracks():
        if t in skip or t.GetNetname() == net:
            continue
        if isinstance(t, p.PCB_VIA):
            if (t.GetPosition() - pos).EuclideanNorm() < radius + t.GetWidth(layer) // 2 + GAP:
                return False
        elif t.GetLayer() == layer and t.HitTest(pos, radius + GAP):
            return False
    for f in board.GetFootprints():
        for a in f.Pads():
            if a.GetNetname() != net and a.IsOnLayer(layer) and \
                    a.GetEffectivePolygon(layer).Collide(pos, radius + GAP):
                return False
    for z in board.Zones():  # rule areas: module body, USB shell, screw head
        if z.GetIsRuleArea() and z.IsOnLayer(layer) and z.Outline().Collide(pos, radius):
            return False
    return True


placed_tp, labels = [], []
for i, (label, net, near) in enumerate(TP_NETS, 1):
    anchor = fps[near].GetPosition()
    spot = None
    for v in sorted((t for t in board.GetTracks() if isinstance(t, p.PCB_VIA)
                     and t.GetNetname() == net),
                    key=lambda v: (v.GetPosition() - anchor).EuclideanNorm()):
        if free_on(p.B_Cu, v.GetPosition(), TP_R, net) and all(
                (v.GetPosition() - q).EuclideanNorm() > p.FromMM(2.5) for q in placed_tp):
            spot = v.GetPosition()
            break
    if spot is None:  # new via one stub away from a pad of the net
        for a in sorted((a for f in board.GetFootprints() for a in f.Pads()
                         if a.GetNetname() == net and a.IsOnLayer(p.F_Cu)),
                        key=lambda a: (a.GetPosition() - anchor).EuclideanNorm()):
            for k in range(16):
                d = p.FromMM(1.1)
                c = a.GetPosition() + p.VECTOR2I(int(d * math.cos(k * math.pi / 8)),
                                                  int(d * math.sin(k * math.pi / 8)))
                stub = p.PCB_TRACK(board)
                stub.SetStart(a.GetPosition())
                stub.SetEnd(c)
                stub.SetLayer(p.F_Cu)
                stub.SetWidth(p.FromMM(.2))
                stub.SetNet(board.FindNet(net))
                ok = free_on(p.B_Cu, c, TP_R, net) and free_on(p.F_Cu, c, p.FromMM(.3), net) \
                    and all(free_on(p.F_Cu, p.VECTOR2I(
                        a.GetPosition().x + (c.x - a.GetPosition().x) * s // 10,
                        a.GetPosition().y + (c.y - a.GetPosition().y) * s // 10),
                        p.FromMM(.1), net) for s in range(3, 11)) \
                    and all((c - q).EuclideanNorm() > p.FromMM(2.5) for q in placed_tp)
                if ok:
                    board.Add(stub)
                    v = p.PCB_VIA(board)
                    v.SetPosition(c)
                    v.SetWidth(p.FromMM(.6))
                    v.SetDrill(p.FromMM(.3))
                    v.SetNet(board.FindNet(net))
                    board.Add(v)
                    spot = c
                    break
            if spot is not None:
                break
    if spot is None:
        print('No room for a test pad on', net)
        continue
    tp = p.FOOTPRINT(tp_lib)
    tp.SetReference(label)
    tp.SetValue(net)
    tp.SetFPID(p.LIB_ID('TestPoint', 'TestPoint_Pad_D1.0mm'))
    tp.SetPosition(spot)
    board.Add(tp)                      # Flip needs the board (segfaults without)
    tp.Flip(spot, p.FLIP_DIRECTION_TOP_BOTTOM)
    tp.SetBoardOnly(True)
    tp.SetExcludedFromBOM(True)
    tp.SetExcludedFromPosFiles(True)
    tp.SetPath(p.KIID_PATH(f'/tp{i}'))
    tp.SetUuidDirect(p.KIID(f'00000000-0000-4000-8000-{i:012d}'))
    tp.Value().SetVisible(False)
    for g in list(tp.GraphicalItems()):   # the library's ring: label only
        if g.GetLayer() == p.B_SilkS:
            tp.Remove(g)
    tp.Reference().SetTextSize(p.VECTOR2I(p.FromMM(.8), p.FromMM(.8)))
    tp.Reference().SetTextThickness(p.FromMM(.15))
    for a in tp.Pads():
        a.SetNet(board.FindNet(net))
    placed_tp.append(spot)
    labels.append(tp)
print('Bottom test pads:', len(placed_tp), '/', len(TP_NETS))
# Labels go on the first side that clears the other labels, every bottom pad /
# mask opening and the board edge; the fab clips silk over openings anyway.
margin = p.FromMM(.15)
taken = [a.GetBoundingBox() for f in board.GetFootprints() for a in f.Pads()
         if a.IsOnLayer(p.B_Cu)]
silk = [d.GetBoundingBox() for d in board.GetDrawings() if d.GetLayer() == p.B_SilkS]
outline = p.BOX2I(p.VECTOR2I(p.FromMM(.5), p.FromMM(.5)),
                  p.VECTOR2I(p.FromMM(W - 1), p.FromMM(H - 1)))
SIDES = ((0, 1.2), (0, -1.2), (1.5, 0), (-1.5, 0), (1.3, 1.1), (-1.3, 1.1),
         (1.3, -1.1), (-1.3, -1.1))
for tp in labels:
    ref, c = tp.Reference(), tp.GetPosition()

    def fits(dx, dy, avoid):
        ref.SetPosition(c + p.VECTOR2I(p.FromMM(dx), p.FromMM(dy)))
        bb = ref.GetBoundingBox()
        bb.Inflate(margin)
        return outline.Contains(bb) and not any(bb.Intersects(t) for t in avoid)
    # Clear of everything if possible, else at least of other silk.
    next((s for s in SIDES if fits(*s, taken + silk)), None) or \
        next((s for s in SIDES if fits(*s, silk)), None) or fits(*SIDES[0], [])
    silk.append(ref.GetBoundingBox())
for z in list(board.Zones()):
    if not z.GetIsRuleArea():
        board.Remove(z)


def zone(net, layer, box, priority=0):
    z = p.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(p.FromMM(.2))
    z.SetThermalReliefGap(p.FromMM(.25))
    z.SetThermalReliefSpokeWidth(p.FromMM(.3))
    z.SetMinThickness(p.FromMM(.2))
    z.Outline().NewOutline()
    x1, y1, x2, y2 = box
    for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
        z.Outline().Append(p.FromMM(x), p.FromMM(y))
    board.Add(z)


full = (.4, .4, W - .4, H - .4)
zone('GND', p.In1_Cu, full)
zone('+3V3_D', p.In2_Cu, full)
zone('GND', p.F_Cu, full)
zone('GND', p.B_Cu, full)
for t in board.GetTracks():
    if isinstance(t, p.PCB_VIA):
        t.SetViaType(p.VIATYPE_THROUGH)
        t.SetFrontTentingMode(p.TENTING_MODE_TENTED)
        t.SetBackTentingMode(p.TENTING_MODE_TENTED)
    elif p.ToMM(t.GetWidth()) < .15:
        t.SetWidth(p.FromMM(.15))
# Buck ground pins and the USB-C ground / shell tie straight into the pour
# (B8, B12): no thermal spokes.
for f in board.GetFootprints():
    if f.GetReference() in ('U3', 'J1'):
        for a in f.Pads():
            if a.GetNetname() == 'GND':
                a.SetLocalZoneConnection(p.ZONE_CONNECTION_FULL)
p.ZONE_FILLER(board).Fill(board.Zones())
p.SaveBoard(str(ROOT / f'{NAME}.kicad_pcb'), board)
print('Planes: L2 GND, L3 +3V3_D, outer GND pours')
