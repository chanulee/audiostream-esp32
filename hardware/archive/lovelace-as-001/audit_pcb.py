#!/usr/bin/env python3
"""Measure the saved board; do not mutate it."""
import json,math,collections
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'lovelace-as-001.kicad_pcb'));d=json.loads((root/'design.json').read_text())
fp={f.GetReference():f for f in b.GetFootprints()}
assert len(fp)==len(d)
for part in d:
 f=fp[part['ref']];assert abs(p.ToMM(f.GetPosition().x)-part['x'])<1e-6;assert abs(p.ToMM(f.GetPosition().y)-part['y'])<1e-6
 for pad in f.Pads():
  if pad.GetNumber() in part['nets']:assert pad.GetNetname()==part['nets'][pad.GetNumber()]
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
    if .5<x<6.0 and 22<y<32:shell.append(t.GetNetname())
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
checks=[('C1',1,'U1',3,3),('C2',1,'U1',2,1),('C3',1,'U1',2,5),('C10',1,'U2',1,1),('C14',1,'U2',8,1),('C16',1,'U2',20,1),('C18',1,'U2',18,1),('C12',1,'U2',2,1),('C12',2,'U2',4,1),('C13',1,'U2',5,5),('C11',1,'U2',1,5),('C15',1,'U2',8,5),('C17',1,'U2',20,5),('C4',1,'U3',2,2),('C8',1,'U4',1,3),('C9',1,'U4',5,5),('C21',1,'U6',5,1),('C23',1,'U5',5,1)]
measurements=[]
for cap,cp,ic,ip,limit in checks:
 gap=edge_gap(pin(cap,cp),pin(ic,ip));measurements.append({'capacitor':cap,'cap_pin':cp,'ic':ic,'ic_pin':ip,'pad_edge_distance_mm':round(gap,3),'target_max_mm':limit,'pass':gap<=limit})
(root/'reports/decoupling.json').write_text(json.dumps(measurements,indent=2)+'\n')
print('Decoupling pin-distance targets passed:',sum(a['pass'] for a in measurements),'/',len(measurements))
assert all(a['pass'] for a in measurements),'A supply capacitor is outside its pin-distance target'
