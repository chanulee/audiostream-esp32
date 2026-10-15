#!/usr/bin/env python3
"""Measure the saved board; do not mutate it."""
import json,math,collections
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'audiostream-s3.kicad_pcb'));d=json.loads((root/'design.json').read_text())
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
    if .5<x<8.4 and 37<y<47:shell.append(t.GetNetname())
assert not inner,'Signal trace found on a dedicated plane layer'
# No component movement occurred during routing. Schematic/board pin mapping must agree.
result={'placement_readback_matches':True,'inner_signal_tracks':len(inner),'top_shell_trace_endpoints':shell,'non_45_degree_segments':angled,'nets':{n:{'length_mm':round(sum(p.ToMM(t.GetLength()) for t in ts),3),'minimum_width_mm':min(p.ToMM(t.GetWidth()) for t in ts),'vias':vias[n]} for n,ts in sorted(tracks.items())},'warning':'Total net length includes branches; USB impedance/skew requires a pair-specific review using the fabricator stackup.'}
(root/'reports'/'routing.json').write_text(json.dumps(result,indent=2)+'\n')
print('Readback matches source; plane signal tracks =',len(inner),'; non-45-degree segments =',len(angled),'; USB top-shell endpoints =',len(shell))
