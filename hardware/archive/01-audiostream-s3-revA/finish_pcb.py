#!/usr/bin/env python3
"""Import outer-layer routing and fill dedicated inner planes."""
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
board=p.LoadBoard(str(ROOT/'audiostream-s3.kicad_pcb'))
assert p.ImportSpecctraSES(board,str(ROOT/'audiostream-s3.ses'))
assert not any(t.GetLayer() in (p.In1_Cu,p.In2_Cu) and not isinstance(t,p.PCB_VIA) for t in board.GetTracks())
def zone(net,layer,box):
 z=p.ZONE(board);z.SetLayer(layer);z.SetNet(board.FindNet(net));z.SetLocalClearance(p.FromMM(.2));z.SetThermalReliefGap(p.FromMM(.25));z.SetThermalReliefSpokeWidth(p.FromMM(.3));z.SetMinThickness(p.FromMM(.2));z.Outline().NewOutline()
 x1,y1,x2,y2=box
 for x,y in [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
 board.Add(z)
zone('GND',p.In1_Cu,(.5,.5,79.5,59.5))
zone('+3V3_D',p.In2_Cu,(.5,.5,42.5,59.5))
zone('+3V3_A',p.In2_Cu,(43,17,79.5,59.5))
zone('GND',p.F_Cu,(.5,.5,79.5,59.5))
zone('GND',p.B_Cu,(.5,.5,79.5,59.5))
for t in board.GetTracks():
 if isinstance(t,p.PCB_VIA):
  t.SetViaType(p.VIATYPE_THROUGH);t.SetFrontTentingMode(p.TENTING_MODE_TENTED);t.SetBackTentingMode(p.TENTING_MODE_TENTED)
p.ZONE_FILLER(board).Fill(board.Zones());p.SaveBoard(str(ROOT/'audiostream-s3.kicad_pcb'),board)
print('Imported routing; solid inner GND; separate digital / analog inner power areas; filled ground pours')
