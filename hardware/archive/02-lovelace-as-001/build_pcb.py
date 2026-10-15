#!/usr/bin/env python3
"""Generate the KiCad prototype from design.json. Run with KiCad's Python."""
import json, math, os, uuid, shutil, csv
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
LIB=Path(os.environ.get('KICAD_FOOTPRINT_DIR',str(ROOT/'lib')))
data=json.loads((ROOT/'design.json').read_text())
# Stable IDs keep schematic and PCB references linked between regenerations.
uid=lambda s:str(uuid.uuid5(uuid.NAMESPACE_URL,'lovelace-as-001-rev-a/'+s))
root_id=uid('root')
q=lambda s:json.dumps(str(s),ensure_ascii=False)
board=p.BOARD();board.SetCopperLayerCount(4)
settings=board.GetDesignSettings();settings.m_MinClearance=p.FromMM(.2);settings.m_TrackMinWidth=p.FromMM(.15);settings.m_CopperEdgeClearance=p.FromMM(.4)
board.SetFileName(str(ROOT/'lovelace-as-001.kicad_pcb'))
nets={n:p.NETINFO_ITEM(board,n) for n in sorted({n for d in data for n in d['nets'].values()})}
for n in nets.values(): board.Add(n)
footprints={}
for d in data:
 lib,name=d['footprint'].split(':');f=p.FootprintLoad(str(LIB/(lib+'.pretty')),name);assert f,d['footprint']
 f.SetReference(d['ref']);f.SetValue(d['value']);f.SetPath(p.KIID_PATH('/'+root_id+'/'+uid(d['ref'])))
 f.SetOrientationDegrees(d['rot']);f.SetPosition(p.VECTOR2I(p.FromMM(d['x']),p.FromMM(d['y'])))
 f.Value().SetVisible(False)
 if d['ref'].startswith('H'): f.Reference().SetVisible(False)
 for item in list(f.GraphicalItems()):
  if item.GetLayer()==p.Edge_Cuts: item.SetLayer(p.F_Fab)
  if item.GetLayer()==p.F_SilkS:
   bb=item.GetBoundingBox()
   if p.ToMM(bb.GetLeft())<.3 or p.ToMM(bb.GetRight())>54.7 or p.ToMM(bb.GetTop())<.3 or p.ToMM(bb.GetBottom())>54.7:f.Remove(item)
 for pad in f.Pads():
  if d['ref']=='U1' and pad.GetNumber()=='41' and pad.GetAttribute()==p.PAD_ATTRIB_PTH:
   pad.SetDrillSize(p.VECTOR2I(p.FromMM(.3),p.FromMM(.3)))
 if d['ref'] in ['C3','C10','C12','C13','C17','R2','R3','R14','D2','D3','SW1','SW2','SW3','U4','U6']: f.Reference().SetVisible(False)
 # Inboard horizontal reference text keeps the assembly drawing readable.
 f.Reference().SetTextAngle(p.EDA_ANGLE(0,p.DEGREES_T));f.Reference().SetTextSize(p.VECTOR2I(p.FromMM(.8),p.FromMM(.8)))
 f.Reference().SetTextThickness(p.FromMM(.12))
 for pad in f.Pads():
  if pad.GetNumber() in d['nets']:pad.SetNet(nets[d['nets'][pad.GetNumber()]])
 board.Add(f);footprints[d['ref']]=f
 # Ship exact library footprints so the project does not depend on global tables.
 target=ROOT/'lib'/(lib+'.pretty');target.mkdir(exist_ok=True)
 source=LIB/(lib+'.pretty')/(name+'.kicad_mod')
 if source.resolve()!=(target/(name+'.kicad_mod')).resolve():shutil.copyfile(source,target/(name+'.kicad_mod'))
for a,b in [((0,0),(55,0)),((55,0),(55,55)),((55,55),(0,55)),((0,55),(0,0))]:
 s=p.PCB_SHAPE();s.SetShape(p.SHAPE_T_SEGMENT);s.SetStart(p.VECTOR2I(*[p.FromMM(v) for v in a]));s.SetEnd(p.VECTOR2I(*[p.FromMM(v) for v in b]));s.SetLayer(p.Edge_Cuts);s.SetWidth(p.FromMM(.05));board.Add(s)
def text(value,x,y,size=1):
 t=p.PCB_TEXT(board);t.SetText(value);t.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));t.SetTextSize(p.VECTOR2I(p.FromMM(size),p.FromMM(size)));t.SetTextThickness(p.FromMM(.15));t.SetLayer(p.F_SilkS);board.Add(t)
text('LOVELACE / AS-001',40,6,.9);text('Wi-Fi Audio',40,9.5,.8);text('AUX',48.5,48,.8);text('BOOT',7,44,.8);text('RESET',31,33,.8);text('USB-C 5V',4,34.5,.8);text('STATUS',38.5,14,.8);text('OFF  POWER  ON',15.5,54,.8);text('OVP',15.5,30,.8)
def track(a,b,net,width=.25,layer=p.F_Cu):
 t=p.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(p.FromMM(width));t.SetLayer(layer);t.SetNet(nets[net]);board.Add(t)
def pad(ref,num): return next(a for a in footprints[ref].Pads() if a.GetNumber()==str(num))
def pt(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
# Draw the short power stage before autorouting; keep SW on the top copper only.
def join45(a,b,net,width):
 ax,ay=p.ToMM(a.x),p.ToMM(a.y);bx,by=p.ToMM(b.x),p.ToMM(b.y)
 dy=by-ay;dx=bx-ax
 if abs(dx)>=abs(dy):mid=pt(ax+math.copysign(abs(dy),dx),by)
 else:mid=pt(bx,ay+math.copysign(abs(dx),dy))
 if a!=mid:track(a,mid,net,width)
 if mid!=b:track(mid,b,net,width)
track(pad('U3',7).GetPosition(),pt(21.65,43.75),'SW',.25)
join45(pt(21.65,43.75),pad('L1',1).GetPosition(),'SW',.25)
join45(pad('L1',2).GetPosition(),pad('C6',1).GetPosition(),'+3V3_D',.8)
# VIN pin fan-out uses 0.25 mm locally, input cap at the left of U3.
join45(pad('C4',1).GetPosition(),pad('U3',2).GetPosition(),'+5V',.25)
join45(pad('C21',1).GetPosition(),pt(19.75,31.5),'VBUS',.25)
track(pt(19.75,31.5),pt(19.75,32.8),'VBUS',.25)
# Fan out the DAC's tightly spaced analog pins without routing across its charge-pump capacitors.
for num,net,y in [(6,'DAC_L',26.675),(7,'DAC_R',26.025),(8,'+3V3_A',25.375)]:
 v=p.PCB_VIA(board);v.SetPosition(pt(43.0,y));v.SetWidth(p.FromMM(.4));v.SetDrill(p.FromMM(.2));v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetViaType(p.VIATYPE_THROUGH);v.SetNet(nets[net]);board.Add(v)
 track(pad('U2',num).GetPosition(),pt(43.0,y),net,.15)
# A dedicated ground via at every local capacitor and external protection diode.
allpads=[a for f in footprints.values() for a in f.Pads()]
for d in data:
 if not d['ref'].startswith(('C','D')):continue
 for a in footprints[d['ref']].Pads():
  if a.GetNetname()!='GND':continue
  x,y=p.ToMM(a.GetPosition().x),p.ToMM(a.GetPosition().y)
  found=False
  for offset in (1.05,1.25,1.5,1.75):
   for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)):
    vx,vy=x+dx*offset,y+dy*offset
    if not (.8<vx<54.2 and .8<vy<54.2):continue
    good=True
    for other in allpads:
     b=other.GetBoundingBox()
     dist=math.hypot(max(p.ToMM(b.GetLeft())-vx,0,vx-p.ToMM(b.GetRight())),max(p.ToMM(b.GetTop())-vy,0,vy-p.ToMM(b.GetBottom())))
     if dist<.55:good=False;break
    if not good:continue
    v=p.PCB_VIA(board);v.SetPosition(pt(vx,vy));v.SetWidth(p.FromMM(.6));v.SetDrill(p.FromMM(.3));v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(nets['GND']);board.Add(v)
    track(a.GetPosition(),pt(vx,vy),'GND',.3);found=True;break
   if found:break
  assert found, 'No safe ground-via location for '+d['ref']
# USB-C has alternating duplicate D+/D- pads. Route this escape explicitly.
def usb_via(net,x,y,diam,drill):
 v=p.PCB_VIA(board);v.SetPosition(pt(x,y));v.SetWidth(p.FromMM(diam));v.SetDrill(p.FromMM(drill));v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetViaType(p.VIATYPE_THROUGH);v.SetNet(nets[net]);v.SetFrontTentingMode(p.TENTING_MODE_TENTED);v.SetBackTentingMode(p.TENTING_MODE_TENTED);board.Add(v)
track(pad('J1','A6').GetPosition(),pt(8.2,26.75),'USB_DP',.15)
track(pad('J1','B6').GetPosition(),pt(8.2,27.75),'USB_DP',.15)
track(pt(8.2,26.75),pt(8.2,27.75),'USB_DP',.2)
usb_via('USB_DP',8.2,27.75,.6,.3)
for num,y in [('A7',27.25),('B7',26.25)]:
 track(pad('J1',num).GetPosition(),pt(7.3,y),'USB_DM',.15)
 usb_via('USB_DM',7.3,y,.4,.2)
track(pt(7.3,26.25),pt(7.3,27.25),'USB_DM',.2,p.B_Cu)
# Keep screw heads and antenna free of copper on every layer.
for x,y in [(4,4),(51,4),(4,51),(51,51)]:
 z=p.ZONE(board);z.SetIsRuleArea(True);z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False);z.SetLayerSet(p.LSET.AllCuMask());z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowZoneFills(True)
 z.Outline().NewOutline()
 for i in range(32):
  a=i*2*math.pi/32;z.Outline().Append(p.FromMM(x+3.5*math.cos(a)),p.FromMM(y+3.5*math.sin(a)))
 board.Add(z)
# Only the USB pin row may carry top copper; shell connections use bottom / plane.
z=p.ZONE(board);z.SetIsRuleArea(True);z.SetLayer(p.F_Cu);z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False);z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowZoneFills(True);z.Outline().NewOutline()
for x,y in [(.5,22),(6.0,22),(6.0,32),(.5,32)]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
board.Add(z)
for a in footprints['J1'].Pads():
 if a.GetNetname()=='GND':a.SetLocalZoneConnection(p.ZONE_CONNECTION_FULL)
# Reserve the copper edge band in the router as well as in KiCad rules.
for box in [(0,0,55,.5),(0,54.5,55,55),(0,0,.5,55),(54.5,0,55,55)]:
 z=p.ZONE(board);z.SetIsRuleArea(True);z.SetLayerSet(p.LSET.AllCuMask());z.SetDoNotAllowPads(False);z.SetDoNotAllowFootprints(False);z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowZoneFills(True);z.Outline().NewOutline()
 x1,y1,x2,y2=box
 for x,y in [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
 board.Add(z)
p.SaveBoard(str(ROOT/'lovelace-as-001.kicad_pcb'),board)
board.SetCopperLayerCount(2)
assert p.ExportSpecctraDSN(board,str(ROOT/'lovelace-as-001.dsn'))
board.SetCopperLayerCount(4)
# Self-contained symbols: named physical pins, labelled connections, explicit NCs.
libdefs=[];instances=[];labels=[];ncs=[];flags=[]
major=[d for d in data if d['ref'] in ['U1','U2','U3','U4','U5','U6','J1','J2','J3']]
minor=[d for d in data if d not in major and d['kind']!='mech']
locs={'U1':(65,85),'U2':(195,75),'U3':(310,40),'U4':(400,40),'U5':(310,90),'J1':(400,110),'J2':(505,40),'J3':(505,80),'U6':(505,130)}
for i,d in enumerate(minor):locs[d['ref']]=(55+(i%7)*75,200+(i//7)*26)
for d in major+minor:
 ref=d['ref'];sym='AudioStream:'+ref;x,y=[round(v/1.27)*1.27 for v in locs[ref]]
 pins=list(d['pin_names']) if d['pin_names'] else list(d['nets'])
 if ref=='J1':pins+=['A8','B8']
 N=len(pins);rows=math.ceil(N/2);height=max(5.08,(rows+1)*1.27)
 pin_items=[];pinpos=[]
 for i,num in enumerate(pins):
  left=i<rows;row=i if left else i-rows;px=-15.24 if left else 15.24;py=height-2.54*(row+1)
  name=d['pin_names'].get(num,num);net=d['nets'].get(num)
  typ='passive'
  if ref=='U1':typ='power_in' if num in ['1','2','40','41'] else ('output' if num in ['19','20','21','37'] else 'bidirectional')
  if ref=='U2':typ='power_in' if num in ['1','3','8','9','19','20'] else ('output' if num in ['5','6','7','18'] else 'input' if num in ['10','11','12','13','14','15','16','17'] else 'passive')
  if ref=='U3':typ={'1':'power_in','2':'power_in','3':'input','4':'power_in','5':'input','6':'input','7':'power_out','8':'open_collector','9':'power_in'}[num]
  if ref=='U6':typ={'1':'input','2':'input','3':'open_collector','4':'open_collector','5':'power_in','6':'power_out','7':'passive','8':'power_in','9':'passive','10':'passive'}[num]
  if ref=='U4':typ={'1':'power_in','2':'power_in','3':'input','4':'no_connect','5':'power_out'}[num]
  pin_items.append(f'(pin {typ} line (at {px} {py:.3f} {0 if left else 180}) (length 5.08) (name {q(name)} (effects (font (size 1 1)))) (number {q(num)} (effects (font (size 1 1)))))')
  ax=x+px;ay=y-py;ex=ax+(-7.62 if left else 7.62)
  if net:
   labels.append(f'(wire (pts (xy {ax:.3f} {ay:.3f}) (xy {ex:.3f} {ay:.3f})) (stroke (width 0) (type default)) (uuid {q(uid(ref+num+"wire"))}))')
   labels.append(f'(label {q(net)} (at {ex:.3f} {ay:.3f} {0 if left else 180}) (effects (font (size 1 1)) (justify {"left" if left else "right"} bottom)) (uuid {q(uid(ref+num+"label"))}))')
  else:ncs.append(f'(no_connect (at {ax:.3f} {ay:.3f}) (uuid {q(uid(ref+num+"nc"))}))')
  pinpos.append(num)
 libdefs.append(f'''(symbol {q(sym)} (pin_names (offset 0.5)) (in_bom yes) (on_board yes)
 (property "Reference" {q(ref.rstrip('0123456789'))} (at 0 {height+3:.3f} 0) (effects (font (size 1.27 1.27))))
 (property "Value" {q(d['value'])} (at 0 {-height-3:.3f} 0) (effects (font (size 1 1))))
 (property "Footprint" {q(d['footprint'])} (at 0 0 0) (effects (font (size 1 1)) hide))
 (symbol {q(ref+'_0_1')} (rectangle (start -10.16 {height:.3f}) (end 10.16 {-height:.3f}) (stroke (width .254) (type default)) (fill (type background))))
 (symbol {q(ref+'_1_1')} {''.join(pin_items)}))''')
 instances.append(f'''(symbol (lib_id {q(sym)}) (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {q(uid(ref))})
 (property "Reference" {q(ref)} (at {x} {y-height-3:.3f} 0) (effects (font (size 1.27 1.27))))
 (property "Value" {q(d['value'])} (at {x} {y+height+3:.3f} 0) (effects (font (size 1 1))))
 (property "Footprint" {q(d['footprint'])} (at {x} {y} 0) (effects (font (size 1 1)) hide))
 {''.join('(pin '+q(n)+' (uuid '+q(uid(ref+n+'pin'))+'))' for n in pinpos)}
 (instances (project "lovelace-as-001" (path {q('/'+root_id)} (reference {q(ref)}) (unit 1)))))''')
# Power source flags explicitly document USB power and the common real ground.
for i,net in enumerate(['VBUS','GND','+3V3_D']):
 name='Flag'+str(i);sym='AudioStream:'+name;x=round((300+i*40)/1.27)*1.27;y=round(155/1.27)*1.27
 libdefs.append(f'(symbol {q(sym)} (in_bom no) (on_board no) (property "Reference" "#FLG" (at 0 3 0) (effects (font (size 1 1)) hide)) (property "Value" "PWR_FLAG" (at 0 5 0) (effects (font (size 1 1)))) (symbol {q(name+"_1_1")} (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))')
 instances.append(f'(symbol (lib_id {q(sym)}) (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (uuid {q(uid(name))}) (property "Reference" {q("#FLG0"+str(i))} (at {x} {y} 0) (effects (font (size 1 1)) hide)) (property "Value" "PWR_FLAG" (at {x} {y-3} 0) (effects (font (size 1 1)))) (pin "1" (uuid {q(uid(name+"pin"))})) (instances (project "lovelace-as-001" (path {q("/"+root_id)} (reference {q("#FLG0"+str(i))}) (unit 1)))))')
 labels.append(f'(label {q(net)} (at {x} {y} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {q(uid(name+"label"))}))')
schematic=f'''(kicad_sch (version 20250114) (generator "eeschema") (uuid {q(root_id)}) (paper "A2")
 (title_block (title "LOVELACE / AS-001") (rev "AS-001") (comment 1 "USB-C 5V; OVP eFuse + POWER switch; GPIO21 STATUS; no A2DP"))
 (lib_symbols {''.join(libdefs)}) {''.join(instances)} {''.join(labels)} {''.join(ncs)}
 (sheet_instances (path "/" (page "1"))))'''
(ROOT/'lovelace-as-001.kicad_sch').write_text(schematic)
project={'board':{'design_settings':{'rules':{'min_clearance':.2,'min_track_width':.15,'min_via_diameter':.4,'min_through_hole_diameter':.2,'min_copper_edge_clearance':.4},'defaults':{'track_width':.25}}},'net_settings':{'classes':[{'name':'Default','clearance':.2,'track_width':.25,'via_diameter':.6,'via_drill':.3,'diff_pair_width':.2,'diff_pair_gap':.15,'diff_pair_via_gap':.25}]},'meta':{'filename':'lovelace-as-001.kicad_pro','version':1}}
(ROOT/'lovelace-as-001.kicad_pro').write_text(json.dumps(project,indent=2))
libs=sorted({d['footprint'].split(':')[0] for d in data})
(ROOT/'fp-lib-table').write_text('(fp_lib_table (version 7)\n'+''.join(f'(lib (name {q(l)}) (type "KiCad") (uri "${{KIPRJMOD}}/lib/{l}.pretty") (options "") (descr "KiCad 10 bundled footprint"))\n' for l in libs)+')\n')
with (ROOT/'bom.csv').open('w') as out:
 w=csv.writer(out);w.writerow(['Designator','Value','Footprint','MPN','Quantity']);
 for d in data:w.writerow([d['ref'],d['value'],d['footprint'],d['mpn'],1])
with (ROOT/'assembly.csv').open('w') as out:
 w=csv.writer(out);w.writerow(['Designator','Mid X','Mid Y','Layer','Rotation']);
 for d in data:
  if d['kind']!='mech':w.writerow([d['ref'],d['x'],d['y'],'Top',d['rot']])
print('Created board, schematic, BOM, assembly positions and DSN')

(ROOT/"AudioStream.kicad_sym").write_text("(kicad_symbol_lib (version 20241209) (generator \"kicad_symbol_editor\") "+"".join(libdefs).replace("AudioStream:","")+")")
(ROOT/"sym-lib-table").write_text('(sym_lib_table (version 7) (lib (name "AudioStream") (type "KiCad") (uri "${KIPRJMOD}/AudioStream.kicad_sym") (options "") (descr "Project symbols, physical pin numbers")))\n')
