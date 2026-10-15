#!/usr/bin/env python3
"""Save a refinement candidate; inspect DRC before replacing the release board."""
from pathlib import Path
import pcbnew as p,shutil
root=Path(__file__).resolve().parent
board=p.LoadBoard(str(root/'lovelace-as-001.kicad_pcb'))
changes=[]
for t in board.GetTracks():
 if not isinstance(t,p.PCB_VIA) and p.ToMM(t.GetWidth())<.15:
  changes.append((t.GetNetname(),p.ToMM(t.GetWidth()),.15));t.SetWidth(p.FromMM(.15))
for f in board.GetFootprints():
 if f.GetReference()=='U3':
  for a in f.Pads():
   if a.GetNetname()=='GND':a.SetLocalZoneConnection(p.ZONE_CONNECTION_FULL)
for t in board.Drawings():
 if isinstance(t,p.PCB_TEXT) and t.GetText()=='BOOT':t.SetPosition(p.VECTOR2I(p.FromMM(7),p.FromMM(44)))
p.ZONE_FILLER(board).Fill(board.Zones())
p.SaveBoard('/tmp/lovelace-as-001-refined.kicad_pcb',board)
shutil.copyfile(root/'lovelace-as-001.kicad_pro','/tmp/lovelace-as-001-refined.kicad_pro')
print('Refinement candidate: widened tracks',changes,'; buck GND direct connection; BOOT label below button')
