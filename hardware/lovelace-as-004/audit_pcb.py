#!/usr/bin/env python3
"""Measure the saved board; do not mutate it."""
import json,math,collections
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent
NAME=json.loads((root/'placement.json').read_text())['board']['name']
b=p.LoadBoard(str(root/f'{NAME}.kicad_pcb'));d=json.loads((root/'design.json').read_text())
# Bottom test pads (finish_pcb.py) are board-only extras, not design parts.
fp={f.GetReference():f for f in b.GetFootprints() if f.GetReference() in {x['ref'] for x in d}}
assert len(fp)==len(d)
for part in d:
 f=fp[part['ref']];assert abs(p.ToMM(f.GetPosition().x)-part['x'])<1e-6;assert abs(p.ToMM(f.GetPosition().y)-part['y'])<1e-6
 for pad in f.Pads():
  if pad.GetNumber() in part['nets']:assert pad.GetNetname()==part['nets'][pad.GetNumber()]
jx=p.ToMM(fp['J1'].GetPosition().x);row=p.ToMM(next(a for a in fp['J1'].Pads() if a.GetNumber()=='A6').GetBoundingBox().GetBottom())
tracks=collections.defaultdict(list);vias=collections.Counter();angled=[];inner=[];shell=[]
for t in b.GetTracks():
 if isinstance(t,p.PCB_VIA):vias[t.GetNetname()]+=1
 else:
  tracks[t.GetNetname()].append(t)
  if t.GetLayer() in (p.In1_Cu,p.In2_Cu):inner.append(str(t.GetUuid()))
  a=t.GetStart();z=t.GetEnd();dx=abs(a.x-z.x);dy=abs(a.y-z.y)
  if min(dx,dy)>p.FromMM(.001) and abs(dx-dy)>p.FromMM(.001):angled.append({'net':t.GetNetname(),'start':[p.ToMM(a.x),p.ToMM(a.y)],'end':[p.ToMM(z.x),p.ToMM(z.y)]})
  if t.GetLayer()==p.F_Cu:
   for x,y in [(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]:
    if jx-4.9<x<jx+4.9 and y>row:shell.append(t.GetNetname())
assert not inner,'Signal trace found on a dedicated plane layer'
# No component movement occurred during routing. Schematic/board pin mapping must agree.
result={'placement_readback_matches':True,'inner_signal_tracks':len(inner),'top_shell_trace_endpoints':shell,'non_45_degree_segments':angled,'nets':{n:{'length_mm':round(sum(p.ToMM(t.GetLength()) for t in ts),3),'minimum_width_mm':min(p.ToMM(t.GetWidth()) for t in ts),'vias':vias[n]} for n,ts in sorted(tracks.items())},'warning':'Total net length includes branches; USB impedance/skew requires a pair-specific review using the fabricator stackup.'}
(root/'reports'/'routing.json').write_text(json.dumps(result,indent=2)+'\n')
print('Readback matches source; plane signal tracks =',len(inner),'; non-45-degree segments =',len(angled),'; USB top-shell endpoints =',len(shell))

# Check supply-pad distances, not only component courtyard distances.
def edge_gap(a,z):
 aa=a.GetBoundingBox();zz=z.GetBoundingBox()
 return math.hypot(max(p.ToMM(aa.GetLeft()-zz.GetRight()),p.ToMM(zz.GetLeft()-aa.GetRight()),0),max(p.ToMM(aa.GetTop()-zz.GetBottom()),p.ToMM(zz.GetTop()-aa.GetBottom()),0))
def pin(ref,num):return next(a for a in fp[ref].Pads() if a.GetNumber()==str(num))
checks=[('C1',1,'U1',3,3),('C2',1,'U1',2,1),('C3',1,'U1',2,5),('C10',1,'U2',1,1),('C14',1,'U2',8,1),('C16',1,'U2',20,1),('C18',1,'U2',18,1),('C12',1,'U2',2,1.5),('C12',2,'U2',4,1.5),('C13',1,'U2',5,1),('C9',1,'U2',1,5),('C15',1,'U2',8,5),('C17',1,'U2',20,5),('C4',1,'U3',2,2),('C8',1,'U4',1,3),('C9',1,'U4',5,3),('C21',1,'U6',5,1.5),('C23',1,'U5',5,1.0),('C24',1,'U7',5,1)]
measurements=[]
for cap,cp,ic,ip,limit in checks:
 gap=edge_gap(pin(cap,cp),pin(ic,ip));measurements.append({'capacitor':cap,'cap_pin':cp,'ic':ic,'ic_pin':ip,'pad_edge_distance_mm':round(gap,3),'target_max_mm':limit,'pass':gap<=limit})
(root/'reports/decoupling.json').write_text(json.dumps(measurements,indent=2)+'\n')
print('Decoupling pin-distance targets passed:',sum(a['pass'] for a in measurements),'/',len(measurements))
assert all(a['pass'] for a in measurements),'A supply capacitor is outside its pin-distance target'

# KiCad DRC leaves lib_footprint_mismatch at "ignore": compare every pad with the
# library copy directly (build_pcb.py only trims silkscreen at the board edge).
lib={'LOVELACE':root/'lib'};kl=Path('/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/footprints')
def padsig(f):return sorted((a.GetNumber(),round(p.ToMM(a.GetFPRelativePosition().x),4),round(p.ToMM(a.GetFPRelativePosition().y),4),round(p.ToMM(a.GetSizeX()),4),round(p.ToMM(a.GetSizeY()),4),a.GetShape(),round(p.ToMM(a.GetDrillSizeX()),3),a.GetAttribute()) for a in f.Pads())
bad=[r for r,f in fp.items() if padsig(f)!=padsig(p.FootprintLoad(str(lib.get(str(f.GetFPID().GetLibNickname()),kl)/(str(f.GetFPID().GetLibNickname())+'.pretty')),str(f.GetFPID().GetLibItemName())))]
print('Footprint pads identical to the library:',len(fp)-len(bad),'/',len(fp))
assert not bad,bad
# AUX jack contacts by distance from the jack face (bottom edge), not by pad
# name: sleeve, ring 2, ring 1, tip (HRO / Shou Han PJ-320D drawings). A TRS
# plug's sleeve spans sleeve + ring 2.
H=json.loads((root/'placement.json').read_text())['board']['h']
order=[a.GetNetname() for a in sorted((a for a in fp['J2'].Pads() if a.GetNumber()),key=lambda a:H-p.ToMM(a.GetPosition().y))]
print('AUX jack contacts, face to rear:',order)
assert order==['GND','GND','LINE_R','LINE_L'],order
# Vias in top-side SMD pads: an unfilled via inside a mask opening wicks the
# paste away (weak joint, 0402 tombstone). KiCad DRC allows same-net via in
# pad; the router is told not to (make_board.sh), this catches regressions.
# Bottom test pads are not assembled and carry their via on purpose; exposed
# pads use footprint thermal-via pads, not board vias.
inpad=[]
for v in (t for t in b.GetTracks() if isinstance(t,p.PCB_VIA)):
 r=v.GetWidth(p.F_Cu)//2
 for f in b.GetFootprints():
  for a in f.Pads():
   if a.GetAttribute()==p.PAD_ATTRIB_SMD and a.IsOnLayer(p.F_Cu) and a.HitTest(v.GetPosition(),r):
    inpad.append(f'{f.GetReference()}.{a.GetNumber()} ({v.GetNetname()})')
print('Vias in top SMD pads:',len(inpad),inpad)
assert not inpad,inpad
# The board's own ID / rev must be printed on the silkscreen: the version
# text lives in the editor's silkscreen.json, so a bump in plan_pcb.py alone
# would leave the old number on the board.
B_=json.loads((root/'placement.json').read_text())['board']
tag=f"{B_['id']} rev {B_['rev']}"
silk=[t.GetText() for t in b.GetDrawings() if isinstance(t,p.PCB_TEXT) and t.GetLayer() in (p.F_SilkS,p.B_SilkS)]
print('Silkscreen version text:',tag,'found' if any(tag in s for s in silk) else 'MISSING')
assert any(tag in s for s in silk),(tag,silk)
