import json,sys
from pathlib import Path
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
LIB=ROOT/'lib'
parts=[]
def part(ref,val,fp,x,y,rot,nets,mpn='',names=None,kind='passive'):
 f=pcb.FootprintLoad(str(LIB/(fp.split(':')[0]+'.pretty')),fp.split(':')[1]); assert f,fp
 pts=[v for a in f.GraphicalItems() if a.GetLayer()==pcb.F_CrtYd for v in (a.GetStart(),a.GetEnd())]
 xx=[pcb.ToMM(v.x) for v in pts]; yy=[pcb.ToMM(v.y) for v in pts]
 box=[min(xx),min(yy),max(xx),max(yy)]
 if ref=='U1': box=[-9.75,-6.75,9.75,13.45]
 p=dict(ref=ref,value=val,footprint=fp,x=x,y=y,rot=rot,nets={str(k):v for k,v in nets.items()},mpn=mpn or val,pin_names=names or {},kind=kind,local_courtyard=box)
 parts.append(p)
 return p
r='Resistor_SMD:R_0603_1608Metric'; c='Capacitor_SMD:C_0603_1608Metric'; cb='Capacitor_SMD:C_0805_2012Metric'
def R(ref,val,x,y,a,b,rot=0): return part(ref,val,r,x,y,rot,{1:a,2:b},'Yageo '+val+' 0603 1%')
def C(ref,val,x,y,a,b='GND',rot=0,big=False):return part(ref,val,cb if big else c,x,y,rot,{1:a,2:b},val+' X7R 10V '+('0805' if big else '0603'))
module_names=['GND','3V3','EN','GPIO4','GPIO5','GPIO6','GPIO7','GPIO15','GPIO16','GPIO17','GPIO18','GPIO8','GPIO19','GPIO20','GPIO3','GPIO46','GPIO9','GPIO10','GPIO11','GPIO12','GPIO13','GPIO14','GPIO21','GPIO47','GPIO48','GPIO45','GPIO0','GPIO35','GPIO36','GPIO37','GPIO38','GPIO39','GPIO40','GPIO41','GPIO42','RXD0','TXD0','GPIO2','GPIO1','GND','EP_GND']
part('U1','ESP32-S3-WROOM-1-N16R8','RF_Module:ESP32-S3-WROOM-1',25,6.75,0,{1:'GND',2:'+3V3_D',3:'EN',13:'USB_DM_MCU',14:'USB_DP_MCU',19:'BCLK_SRC',20:'DATA_SRC',21:'LRCLK_SRC',27:'BOOT',36:'UART_RX',37:'UART_TX',40:'GND',41:'GND'},names={str(i+1):n for i,n in enumerate(module_names)},kind='module')
dac_names=['CPVDD','CAPP','CPGND','CAPM','VNEG','OUTL','OUTR','AVDD','AGND','DEMP','FLT','SCK','BCK','DIN','LRCK','FMT','XSMT','LDOO','DGND','DVDD']
part('U2','PCM5102APWR','Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',56,30,180,{1:'+3V3_A',2:'CAPP',3:'GND',4:'CAPM',5:'VNEG',6:'DAC_L',7:'DAC_R',8:'+3V3_A',9:'GND',10:'GND',11:'GND',12:'GND',13:'BCLK',14:'DATA',15:'LRCLK',16:'GND',17:'XSMT',18:'LDOO',19:'GND',20:'+3V3_D'},names={str(i+1):n for i,n in enumerate(dac_names)},kind='ic')
part('U3','TPS62162DSGR','Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm_ThermalVias',25,40,0,{1:'GND',2:'+5V',3:'+5V',4:'GND',5:'GND',6:'+3V3_D',7:'SW',9:'GND'},names={'1':'PGND','2':'VIN','3':'EN','4':'AGND','5':'FB','6':'VOS','7':'SW','8':'PG','9':'EP_GND'},kind='power')
part('L1','2.2uH','Inductor_SMD:L_Coilcraft_LPS4018',30.5,40,0,{1:'SW',2:'+3V3_D'},'LPS4018-222MRC',kind='power')
part('U4','TLV75533PDBVR','Package_TO_SOT_SMD:SOT-23-5',54,44,0,{1:'+5V',2:'GND',3:'+5V',5:'+3V3_A'},names={'1':'IN','2':'GND','3':'EN','4':'NC','5':'OUT'},kind='power')
part('J1','HRO TYPE-C-31-M-12','Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',4.75,42,270,{**{p:'GND' for p in ['A1','A12','B1','B12','SH']},**{p:'VBUS' for p in ['A4','A9','B4','B9']},'A5':'CC1','B5':'CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM'},kind='connector')
part('J2','SJ1-3523N','Connector_Audio:Jack_3.5mm_CUI_SJ1-3523N_Horizontal',76,30,90,{'T':'LINE_L','R':'LINE_R','S':'GND'},kind='connector')
part('U5','USBLC6-2SC6','Package_TO_SOT_SMD:SOT-23-6',13.5,42,0,{1:'USB_DP',2:'GND',3:'USB_DM',4:'USB_DM',5:'VBUS',6:'USB_DP'},names={'1':'IO1','2':'GND','3':'IO2','4':'IO2','5':'VBUS','6':'IO1'},kind='ic')
part('F1','MF-MSMF075-2','Fuse:Fuse_1812_4532Metric',13.5,51,0,{1:'VBUS',2:'+5V'},kind='power')
for ref,y,n in [('SW1',28,'BOOT'),('SW2',28,'EN')]:
 part(ref,'TL3342F160QG','Button_Switch_SMD:SW_SPST_TL3342',7 if ref=='SW1' else 40,y,0,{1:n,2:'GND'},kind='connector')
part('J3','UART recovery','Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical',41,48,0,{1:'GND',2:'UART_TX',3:'UART_RX',4:'+3V3_D'},'2.54mm male header',kind='connector')
R('R1','5.1k',8.5,35,'CC1','GND');R('R2','5.1k',8.5,32.5,'CC2','GND')
R('R3','22',12,18,'USB_DP','USB_DP_MCU');R('R4','22',12,15.5,'USB_DM','USB_DM_MCU')
R('R5','10k',12.5,8.5,'+3V3_D','EN');C('C1','1uF',12.5,5.5,'EN');C('C2','100nF',13,2.75,'+3V3_D');C('C3','10uF',12,12,'+3V3_D',big=True)
R('R6','10k',38.5,21.5,'+3V3_D','BOOT')
R('R7','33',22.5,23.5,'BCLK_SRC','BCLK');R('R8','33',26,23.5,'DATA_SRC','DATA');R('R9','33',29.5,23.5,'LRCLK_SRC','LRCLK')
C('C4','10uF',21.75,39.5,'+5V',rot=180,big=True);C('C5','10uF',18,35.5,'+3V3_D',big=True)
part('C6','47uF','Capacitor_SMD:C_1206_3216Metric',36.5,40,0,{1:'+3V3_D',2:'GND'},'GRM31CR61A476KE15L')
C('C7','10uF',20.5,51,'+5V',big=True)
C('C8','1uF',50,44,'+5V');C('C9','10uF',58,44,'+3V3_A',big=True)
C('C10','100nF',61.5,33.75,'+3V3_A');C('C11','10uF',65,36,'+3V3_A',big=True)
C('C12','2.2uF',61.5,31,'CAPP','CAPM',rot=90)
C('C13','2.2uF',61.5,24,'VNEG',rot=90)
C('C14','100nF',61.5,28,'+3V3_A');C('C15','10uF',65,26,'+3V3_A',big=True)
C('C16','100nF',50.5,33.5,'+3V3_D');C('C17','10uF',46.5,33.5,'+3V3_D',big=True)
C('C18','100nF',50.5,31,'LDOO')
R('R10','10k',47.5,28.5,'+3V3_D','XSMT')
R('R11','470',64,19,'DAC_L','LINE_L');R('R12','470',67.5,19,'DAC_R','LINE_R')
C('C19','2.2nF',71,19,'LINE_L');C('C20','2.2nF',74.5,19,'LINE_R')
for ref,x,y,net in [('D1',12.25,37.5,'VBUS'),('D2',71.5,21.5,'LINE_L'),('D3',75,21.5,'LINE_R')]:
 part(ref,'PESD5V0S1BA','Diode_SMD:D_SOD-323',x,y,0,{1:net,2:'GND'},'PESD5V0S1BA,115',names={'1':'K1','2':'K2'})
for i,(x,y) in enumerate([(4,4),(76,4),(4,56),(76,56)],1):
 part('H'+str(i),'M3','MountingHole:MountingHole_3.2mm_M3',x,y,0,{},kind='mech')
plan={'board':{'w':80,'h':60,'edge_clearance':0.5,'grid':0.25},'zones':{},'keepouts':[{'name':'antenna - no copper / parts / metal','rect':[1,-21,49,0],'allow':['U1']}], 'parts':[],'near':[],'apart':[{'a':'L1','b':'U2','min':15,'why':'B15 buck inductor at least 15 mm from DAC analog stage'}]}
for p in parts:
 b=p['local_courtyard'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
 import math
 a=math.radians(p['rot']); px=p['x']+cx*math.cos(a)+cy*math.sin(a);py=p['y']-cx*math.sin(a)+cy*math.cos(a)
 plan['parts'].append(dict(ref=p['ref'],x=round(px,5),y=round(-py,5),w=b[2]-b[0],h=b[3]-b[1],rot=p['rot'],grid=0.005,**{'class':p['kind']},allow_overhang=p['ref'] in ('U1','J2')))
plan['board']['origin']=[0,-60]
plan['keepouts']=[{'name':'antenna external keepout','rect':[1,0,49,21],'allow':['U1']}]+[{'name':'M3 screw '+str(i),'circle':[x,-y,3.5],'allow':['H'+str(i)]} for i,(x,y) in enumerate([(4,4),(76,4),(4,56),(76,56)],1)]
for a,b,dist in [('C2','U1',1),('C3','U1',5),('C10','U2',1),('C14','U2',1),('C16','U2',1),('C18','U2',1),('C12','U2',1),('C13','U2',5),('C11','U2',5),('C15','U2',5),('C17','U2',5),('C8','U4',3),('C9','U4',5),('C4','U3',2),('C5','U3',5),('C6','L1',3),('U5','J1',5),('R1','J1',5),('R2','J1',5),('D1','J1',5),('D2','J2',5),('D3','J2',5),('L1','U3',3)]:
 plan['near'].append(dict(a=a,b=b,max=dist,why='B1 supply decoupling / B9 protection / B14 CC termination' ))
(ROOT/'design.json').write_text(json.dumps(parts,indent=2)+'\n');(ROOT/'placement.json').write_text(json.dumps(plan,indent=2)+'\n')
print(len(parts),'components')
