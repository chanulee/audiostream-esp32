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
 if ref.startswith('H'):
  item=next(a for a in f.GraphicalItems() if a.GetLayer()==pcb.F_CrtYd);bb=item.GetBoundingBox();box=[pcb.ToMM(v) for v in [bb.GetLeft(),bb.GetTop(),bb.GetRight(),bb.GetBottom()]]
 if ref=='U1': box=[-9.75,-6.75,9.75,13.45]
 p=dict(ref=ref,value=val,footprint=fp,x=x,y=y,rot=rot,nets={str(k):v for k,v in nets.items()},mpn=mpn or val,pin_names=names or {},kind=kind,local_courtyard=box)
 parts.append(p)
 return p
r='Resistor_SMD:R_0603_1608Metric'; c='Capacitor_SMD:C_0603_1608Metric'; cb='Capacitor_SMD:C_0805_2012Metric'
def R(ref,val,x,y,a,b,rot=0): return part(ref,val,r,x,y,rot,{1:a,2:b},'Yageo '+val+' 0603 1%')
def C(ref,val,x,y,a,b='GND',rot=0,big=False):return part(ref,val,cb if big else c,x,y,rot,{1:a,2:b},val+' X7R 10V '+('0805' if big else '0603'))
module_names=['GND','3V3','EN','GPIO4','GPIO5','GPIO6','GPIO7','GPIO15','GPIO16','GPIO17','GPIO18','GPIO8','GPIO19','GPIO20','GPIO3','GPIO46','GPIO9','GPIO10','GPIO11','GPIO12','GPIO13','GPIO14','GPIO21','GPIO47','GPIO48','GPIO45','GPIO0','GPIO35','GPIO36','GPIO37','GPIO38','GPIO39','GPIO40','GPIO41','GPIO42','RXD0','TXD0','GPIO2','GPIO1','GND','EP_GND']
part('U1','ESP32-S3-WROOM-1-N16R8','RF_Module:ESP32-S3-WROOM-1',25,6.75,0,{1:'GND',2:'+3V3_D',3:'EN',13:'USB_DM_MCU',14:'USB_DP_MCU',19:'BCLK_SRC',20:'DATA_SRC',21:'LRCLK_SRC',23:'STATUS_GPIO',27:'BOOT',36:'UART_RX',37:'UART_TX',40:'GND',41:'GND'},names={str(i+1):n for i,n in enumerate(module_names)},kind='module')
dac_names=['CPVDD','CAPP','CPGND','CAPM','VNEG','OUTL','OUTR','AVDD','AGND','DEMP','FLT','SCK','BCK','DIN','LRCK','FMT','XSMT','LDOO','DGND','DVDD']
part('U2','PCM5102APWR','Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',56,30,180,{1:'+3V3_A',2:'CAPP',3:'GND',4:'CAPM',5:'VNEG',6:'DAC_L',7:'DAC_R',8:'+3V3_A',9:'GND',10:'GND',11:'GND',12:'GND',13:'BCLK',14:'DATA',15:'LRCLK',16:'GND',17:'XSMT',18:'LDOO',19:'GND',20:'+3V3_D'},names={str(i+1):n for i,n in enumerate(dac_names)},kind='ic')
part('U3','TPS62162DSGR','Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm_ThermalVias',25,40,0,{1:'GND',2:'+5V',3:'+5V',4:'GND',5:'GND',6:'+3V3_D',7:'SW',9:'GND'},names={'1':'PGND','2':'VIN','3':'EN','4':'AGND','5':'FB','6':'VOS','7':'SW','8':'PG','9':'EP_GND'},kind='power')
part('L1','2.2uH','Inductor_SMD:L_Coilcraft_LPS4018',30.5,40,0,{1:'SW',2:'+3V3_D'},'LPS4018-222MRC',kind='power')
part('U4','TLV75533PDBVR','Package_TO_SOT_SMD:SOT-23-5',54,44,0,{1:'+5V',2:'GND',3:'+5V',5:'+3V3_A'},names={'1':'IN','2':'GND','3':'EN','4':'NC','5':'OUT'},kind='power')
part('J1','HRO TYPE-C-31-M-12','Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',4.75,42,270,{**{p:'GND' for p in ['A1','A12','B1','B12','SH']},**{p:'VBUS' for p in ['A4','A9','B4','B9']},'A5':'CC1','B5':'CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM'},kind='connector')
part('J2','SJ1-3523N','Connector_Audio:Jack_3.5mm_CUI_SJ1-3523N_Horizontal',76,30,90,{'T':'LINE_L','R':'LINE_R','S':'GND'},kind='connector')
part('U5','USBLC6-2SC6','Package_TO_SOT_SMD:SOT-23-6',13.5,42,0,{1:'USB_DP',2:'GND',3:'USB_DM',4:'USB_DM',5:'+5V',6:'USB_DP'},names={'1':'IO1','2':'GND','3':'IO2','4':'IO2','5':'VBUS','6':'IO1'},kind='ic')
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
for ref,x,y,net in [('D1',12.25,37.5,'+5V'),('D2',71.5,21.5,'LINE_L'),('D3',75,21.5,'LINE_R')]:
 part(ref,'PESD5V0S1BA','Diode_SMD:D_SOD-323',x,y,0,{1:net,2:'GND'},'PESD5V0S1BA,115',names={'1':'K1','2':'K2'})
part('U6','TPS259470ARPWR','LOVELACE:TPS25947_RPW0010A',20,34,0,{1:'POWER_EN',2:'OVLO',5:'VBUS',6:'+5V',7:'DVDT',8:'GND',9:'ILIM'},names={'1':'EN_UVLO','2':'OVLO','3':'AUXOFF','4':'FLT','5':'IN','6':'OUT','7':'DVDT','8':'GND','9':'ILIM','10':'ITIMER'},kind='power')
part('SW3','JS102011SAQN','Button_Switch_SMD:SW_SPDT_CK_JS102011SAQN',15.5,50.75,0,{1:'GND',2:'POWER_EN',3:'EN_FEED'},kind='connector')
R('R13','348k',17,33.5,'VBUS','OVLO');R('R14','100k',17,36,'OVLO','GND',rot=180)
R('R15','4.99k',23.75,34.5,'ILIM','GND');R('R16','390k',23.75,31,'VBUS','EN_FEED');R('R17','1M',27.25,29.25,'POWER_EN','GND')
C('C21','100nF',20,31.5,'VBUS');C('C22','10nF',23.75,37.5,'DVDT')
parts[-2]['mpn']='100nF X7R 50V 0603';parts[-1]['mpn']='10nF C0G 50V 0603'
R('R18','1k',35,17.5,'STATUS_GPIO','STATUS_A')
part('D4','AP2012SGC','LED_SMD:LED_0805_2012Metric',35,14,0,{1:'GND',2:'STATUS_A'},names={'1':'K','2':'A'})
C('C23','100nF',14.25,27,'+5V')
R('R19','100k',31,47.5,'+5V','GND')
for part_data in parts:
 if part_data['ref'] in ['R13','R14']:part_data['mpn']=part_data['value']+' 0603 0.1% thin-film'
positions={'U1':(22.5,6.75),'U2':(39,27),'U3':(20,44),'L1':(24.25,45.25),'U4':(40,45),'J1':(2.35,27),'J2':(51,39),'U5':(10.5,27),'SW1':(7,39.5),'SW2':(31,37.5),'J3':(33,51.5),'R1':(8,20.25),'R2':(8.75,33.75),'R3':(10,18),'R4':(10,15.5),'R5':(10.5,10.5),'C1':(11,4.75),'C2':(11,2),'C3':(9.5,7.75),'R6':(35,21.5),'R7':(20,23.5),'R8':(23.5,23.5),'R9':(27,23.5),'C4':(16.75,43.5),'C5':(16,39),'C6':(31.5,44),'C7':(20,39),'C8':(36,45),'C9':(44,48),'C10':(44.5,30.5),'C11':(48,31),'C12':(44,27.75),'C13':(47.5,27.5),'C14':(44.5,24.5),'C15':(48,23),'C16':(33.5,30.5),'C17':(29.5,31.5),'C18':(33.5,28),'R10':(30,27),'R11':(43.5,18.75),'R12':(47,18.75),'C19':(43.5,16),'C20':(47,16),'D1':(24,26.75),'D2':(40.5,34.75),'D3':(40.5,41.75)}
for part_data in parts:
 if part_data['ref'] in positions:part_data['x'],part_data['y']=positions[part_data['ref']]
 if part_data['ref'] in ['C1','C2','C3','C16','C17','C18','C8']:part_data['rot']=180
 if part_data['ref'] in ['J3','D2','D3']:part_data['rot']=90 if part_data['ref']=='J3' else 180
for i,(x,y) in enumerate([(4,4),(51,4),(4,51),(51,51)],1):
 part('H'+str(i),'M3','MountingHole:MountingHole_3.2mm_M3',x,y,0,{},kind='mech')
plan={'board':{'w':55,'h':55,'edge_clearance':0.5,'grid':0.25},'zones':{},'keepouts':[{'name':'antenna - no copper / parts / metal','rect':[1,-21,49,0],'allow':['U1']}], 'parts':[],'near':[],'apart':[{'a':'L1','b':'U2','min':15,'why':'B15 buck inductor at least 15 mm from DAC analog stage'}]}
for p in parts:
 b=p['local_courtyard'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
 import math
 a=math.radians(p['rot']); px=p['x']+cx*math.cos(a)+cy*math.sin(a);py=p['y']-cx*math.sin(a)+cy*math.cos(a)
 plan['parts'].append(dict(ref=p['ref'],x=round(px,5),y=round(-py,5),w=b[2]-b[0],h=b[3]-b[1],rot=p['rot'],grid=(0.005 if p['ref'] in ('U1','J1','J2','J3','SW3') else 0.25),**{'class':p['kind']},locked=p['ref'] in ('U1','J1','J2','SW3','D4'),allow_overhang=p['ref'] in ('U1','J1','J2')))
plan['board']['origin']=[0,-55]
plan['keepouts']=[{'name':'antenna external keepout','rect':[-1.5,0,46.5,21],'allow':['U1']}]+[{'name':'M3 screw '+str(i),'circle':[x,-y,3.5],'allow':['H'+str(i)]} for i,(x,y) in enumerate([(4,4),(51,4),(4,51),(51,51)],1)]
for a,b,dist in [('C1','U1',3),('R5','U1',5),('C2','U1',1),('C3','U1',5),('C10','U2',1),('C14','U2',1),('C16','U2',1),('C18','U2',1),('C12','U2',1),('C13','U2',5),('C11','U2',5),('C15','U2',5),('C17','U2',5),('C8','U4',3),('C9','U4',5),('C4','U3',2),('C5','U3',5),('C6','L1',3),('U5','J1',5),('R1','J1',5),('R2','J1',5),('D1','U6',5),('D2','J2',5),('D3','J2',5),('L1','U3',3),('C23','U5',1),('C21','U6',1),('R13','U6',2),('R14','U6',2),('R15','U6',2),('C22','U6',3)]:
 plan['near'].append(dict(a=a,b=b,max=dist,why='B1 supply decoupling / B9 protection / B14 CC termination' ))
(ROOT/'design.json').write_text(json.dumps(parts,indent=2)+'\n');(ROOT/'placement.json').write_text(json.dumps(plan,indent=2)+'\n')
print(len(parts),'components')
