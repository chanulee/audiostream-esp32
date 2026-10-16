#!/usr/bin/env python3
"""LOVELACE netlist + placement source of truth (board ID / rev: BOARD_ID).

Run with KiCad's Python. Writes design.json (parts, nets, footprint origins)
and placement.json (pcb-layout-skill checker input, courtyard centres, y up).

Floorplan (KiCad coordinates, y down, board origin top-left):
  top edge      ESP32-WROVER-E antenna overhangs the board edge
  left strip    3V3 / EN satellites on the module's left pins
  right column  PCM5102A, I2S series R, analog LDO, status LED, BOOT
  bottom edge   USB-C power | POWER switch | 3.5 mm AUX  (all user I/O here)
"""
import json, math, os
from pathlib import Path
import pcbnew as pcb

ROOT = Path(__file__).resolve().parent
LIB = ROOT / 'lib'
KICAD_LIB = Path(os.environ.get(
    'KICAD_FOOTPRINT_DIR',
    '/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/footprints'))
# --- Version: the one place the board name and revision are set ------------
# AS-<n> is a new design (netlist or outline changed before it was ordered);
# rev A, B, ... are changes to a design after it has been ordered. Everything
# downstream reads these from placement.json: KiCad file names, silkscreen,
# title blocks, renders, the release zip and the silkscreen editor.
BOARD_ID, BOARD_REV = 'AS-006', 'A'
NAME = 'lovelace-' + BOARD_ID.lower()
W, H = 36.0, 40.0
# autoplace.py writes positions.json (board size + part coordinates).
POSITIONS = ROOT / 'positions.json'
placed = json.loads(POSITIONS.read_text()) if POSITIONS.exists() else None
if placed:
    W, H = placed['board']
# On-board part of the module: the board edge sits 0.77 mm above pin 1 so the
# whole PCB antenna overhangs (Espressif placement option 1, no copper under it).
U1_Y = 9.48
U1_ONBOARD = [-9.81, -9.48, 9.81, 16.01]

parts = []


def load(fp):
    lib, name = fp.split(':')
    for base in (LIB, KICAD_LIB):
        path = base / (lib + '.pretty')
        if (path / (name + '.kicad_mod')).exists():
            f = pcb.FootprintLoad(str(path), name)
            assert f, fp
            return f
    raise FileNotFoundError(fp)


def courtyard(f):
    boxes = [a.GetBoundingBox() for a in f.GraphicalItems()
             if a.GetLayer() == pcb.F_CrtYd]
    assert boxes
    return [min(pcb.ToMM(b.GetLeft()) for b in boxes),
            min(pcb.ToMM(b.GetTop()) for b in boxes),
            max(pcb.ToMM(b.GetRight()) for b in boxes),
            max(pcb.ToMM(b.GetBottom()) for b in boxes)]


def part(ref, val, fp, x, y, rot, nets, mpn='', names=None, kind='passive'):
    box = U1_ONBOARD if ref == 'U1' else courtyard(load(fp))
    parts.append(dict(ref=ref, value=val, footprint=fp, x=x, y=y, rot=rot,
                      nets={str(k): v for k, v in nets.items()},
                      mpn=mpn or val, pin_names=names or {}, kind=kind,
                      local_courtyard=box))


R04 = 'Resistor_SMD:R_0402_1005Metric'
C04 = 'Capacitor_SMD:C_0402_1005Metric'
C08 = 'Capacitor_SMD:C_0805_2012Metric'
C06 = 'Capacitor_SMD:C_0603_1608Metric'


def R(ref, val, x, y, a, b, rot=0, mpn=None):
    part(ref, val, R04, x, y, rot, {1: a, 2: b}, mpn or f'{val} 1% 0402')


def C(ref, val, x, y, a, b='GND', rot=0, big=False, mid=False, mpn=None):
    fp = C08 if big else C06 if mid else C04
    rating = ('X5R 10V 0805' if big else 'X5R 10V 0603' if mid else
              'X5R 10V 0402' if val.endswith('uF') else 'X7R 16V 0402')
    part(ref, val, fp, x, y, rot, {1: a, 2: b}, mpn or f'{val} {rating}')


# --- MCU ------------------------------------------------------------------
module_names = ['GND', '3V3', 'EN', 'SENSOR_VP', 'SENSOR_VN', 'GPIO34',
                'GPIO35', 'GPIO32', 'GPIO33', 'GPIO25', 'GPIO26', 'GPIO27',
                'GPIO14', 'GPIO12', 'GND', 'GPIO13', 'NC', 'NC', 'NC', 'NC',
                'NC', 'NC', 'GPIO15', 'GPIO2', 'GPIO0', 'GPIO4', 'NC', 'NC',
                'GPIO5', 'GPIO18', 'GPIO19', 'NC', 'GPIO21', 'RXD0', 'TXD0',
                'GPIO22', 'GPIO23', 'GND', 'EP_GND']
# I2S leaves the module in the DAC's pin order (SKILL gate 2): GPIO21 BCK,
# GPIO19 DIN, GPIO18 LRCK; GPIO23 drives the status LED, GPIO22 the DAC's
# XSMT soft mute. Firmware Kconfig
# (config/sdkconfig.defaults.lovelace-wrover) must match.
part('U1', 'ESP32-WROVER-E-N8R8', 'LOVELACE:ESP32-WROVER-E', 13.01, U1_Y, 0,
     {1: 'GND', 2: '+3V3_D', 3: 'EN', 15: 'GND', 25: 'BOOT', 30: 'LRCLK',
      31: 'DATA', 33: 'BCLK', 34: 'UART_RX', 35: 'UART_TX', 36: 'XSMT',
      37: 'STATUS_GPIO', 38: 'GND', 39: 'GND'},
     names={str(i + 1): n for i, n in enumerate(module_names)}, kind='module')
# Left strip: 3V3 100 nF at pin 2, bulk, EN RC.
C('C2', '100nF', 2.2, 2.1, '+3V3_D', rot=90)
C('C1', '1uF', 2.2, 4.27, 'EN', rot=90)
C('C3', '10uF', 2.0, 7.25, '+3V3_D', rot=90, mid=True)
R('R5', '10k', 2.2, 10.25, '+3V3_D', 'EN', rot=90)

# --- DAC (right column) --------------------------------------------------
dac_names = ['CPVDD', 'CAPP', 'CPGND', 'CAPM', 'VNEG', 'OUTL', 'OUTR', 'AVDD',
             'AGND', 'DEMP', 'FLT', 'SCK', 'BCK', 'DIN', 'LRCK', 'FMT', 'XSMT',
             'LDOO', 'DGND', 'DVDD']
# SCK=GND selects the internal PLL; FMT=GND I2S; FLT/DEMP=GND normal filter.
# The whole DAC (AVDD, CPVDD and DVDD) runs from the LDO, whose input is held
# up by D5 / C25: on USB unplug the module dies first, the I2S clocks stop and
# the DAC finishes its clock-loss soft mute (datasheet 11.2) before it loses
# power, so unplugging does not pop.
part('U2', 'PCM5102APWR', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm', 28.66, 10.0,
     180, {1: '+3V3_A', 2: 'CAPP', 3: 'GND', 4: 'CAPM', 5: 'VNEG', 6: 'DAC_L',
           7: 'DAC_R', 8: '+3V3_A', 9: 'GND', 10: 'GND', 11: 'GND', 12: 'GND',
           13: 'BCLK', 14: 'DATA', 15: 'LRCLK', 16: 'GND', 17: 'XSMT',
           18: 'LDOO', 19: 'GND', 20: '+3V3_A'},
     names={str(i + 1): n for i, n in enumerate(dac_names)}, kind='ic')
# No I2S series resistors: module-to-DAC traces are ~5 mm, far below the
# ~25 mm critical length of a 1 ns edge.
C('C18', '100nF', 23.82, 12.2, 'LDOO', rot=270)
# Right pin row: AVDD, VNEG, charge-pump flying cap; CPVDD below pin 1. The
# AVDD 10 uF stands right of that column so the top-right corner is free for H1.
C('C15', '10uF', 35.3, 9.5, '+3V3_A', rot=90, mid=True)
C('C14', '100nF', 33.4, 8.0, '+3V3_A', rot=90)
C('C13', '2.2uF', 33.4, 10.2, 'VNEG', rot=90)
C('C12', '2.2uF', 33.4, 12.4, 'CAPP', 'CAPM', rot=90)
C('C10', '100nF', 31.5, 14.4, '+3V3_A')
C('C16', '100nF', 26.2, 14.4, '+3V3_A')
# XSMT pull-down: the DAC stays muted through reset and boot until GPIO22
# drives it high.
R('R10', '10k', 28.4, 14.4, 'GND', 'XSMT')
C('C17', '10uF', 24.35, 17.0, '+3V3_A', rot=90, mid=True)
# Low-noise analog LDO. VIN: 6.0 V recommended max, 6.5 V absolute max; the
# eFuse OVLO window tops out at 6.0 V (see U6).
part('U4', 'TPS7A2033PDBVR', 'Package_TO_SOT_SMD:SOT-23-5', 29.8, 18.0, 0,
     {1: '+5V_DAC', 2: 'GND', 3: '+5V_DAC', 5: '+3V3_A'},
     names={'1': 'IN', '2': 'GND', '3': 'EN', '4': 'NC', '5': 'OUT'},
     kind='power')
C('C8', '1uF', 26.6, 18.0, '+5V_DAC', rot=90)
# Hold-up for the DAC rail: D5 blocks the module's load, C25 keeps the LDO in
# regulation for 220 uF x (4.7 - 3.35 V) / 31 mA = 9.6 ms (5.3 ms from a 4.4 V
# supply); the soft mute needs 150 samples + 0.2 ms = 3.6 ms at 44.1 kHz.
# The diode drop also keeps the LDO input below 5.7 V at the OVLO limit.
part('D5', 'RB551V-30', 'Diode_SMD:D_SOD-323', 34.5, 22.0, 270,
     {1: '+5V_DAC', 2: '+5V'}, 'RB551V-30', names={'1': 'K', '2': 'A'})
part('C25', '220uF', 'Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B', 29.75,
     3.3, 90, {1: '+5V_DAC', 2: 'GND'}, 'T520B227M006ATE025 6.3V polymer',
     names={'1': '+', '2': '-'})
C('C9', '10uF', 33.49, 17.6, '+3V3_A', rot=90, mid=True)
# Line-out RC (470 R / 2.2 nF, ~150 kHz) and ESD at the jack pins.
R('R11', '470', 31.5, 36.4, 'DAC_L', 'LINE_L', rot=270)
C('C19', '2.2nF', 30.2, 36.4, 'LINE_L', rot=90)
R('R12', '470', 26.2, 36.4, 'DAC_R', 'LINE_R', rot=270)
C('C20', '2.2nF', 27.5, 36.4, 'LINE_R', rot=90)
# Each diode sits next to its jack pad: LINE_R (ring) on the left of the jack,
# LINE_L (tip) on the lone pad at the right edge.
for ref, x, y, net in [('D2', 24.5, 30.0, 'LINE_R'), ('D3', 35.5, 26.6, 'LINE_L')]:
    part(ref, 'PESD5V0S1BA', 'Diode_SMD:D_SOD-323', x, y, 90,
         {1: net, 2: 'GND'}, 'PESD5V0S1BA,115', names={'1': 'K1', '2': 'K2'})

# --- Status / buttons -------------------------------------------------------
part('D4', 'KT-0603G', 'LED_SMD:LED_0603_1608Metric', 28.6, 1.5, 0,
     {1: 'GND', 2: 'STATUS_A'}, names={'1': 'K', '2': 'A'})
R('R18', '220', 25.6, 1.5, 'STATUS_GPIO', 'STATUS_A')   # green Vf ~2.9 V at 3.3 V
# One user button on GPIO0: playback / pairing at runtime; held while USB is
# plugged in it selects the ROM download mode (CH340N has no DTR).
part('SW1', 'B3U-1000P', 'Button_Switch_SMD:SW_SPST_B3U-1000P', 26.25, 22.6, 0,
     {1: 'BOOT', 2: 'GND'}, 'Omron B3U-1000P', kind='connector')
R('R6', '10k', 25.0, 25.5, '+3V3_D', 'BOOT')

# --- Bottom edge: USB-C power and AUX --------------------------------------
part('J1', 'HRO TYPE-C-31-M-12',
     'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', 5.35, H - 3.65, 0,
     {**{p: 'GND' for p in ['A1', 'A12', 'B1', 'B12', 'SH']},
      **{p: 'VBUS' for p in ['A4', 'A9', 'B4', 'B9']},
      'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP',
      'A7': 'USB_DM', 'B7': 'USB_DM'}, kind='connector')
# PJ-320D is TRRS. The KiCad pad names do not follow the contacts: the HRO
# and Shou Han drawings put the tip on the lone rear pad (KiCad 'S', 11.3 mm
# from the face), then ring 1 ('T', 10.2 mm), ring 2 ('R1', 6.2 mm) and the
# sleeve ('R2', 3.2 mm, next to the opening). A TRS plug's sleeve spans both
# ring 2 and the sleeve, so both are GND.
# Rot 90 points the nozzle at the bottom edge; the body front sits on the edge.
# Land from the Shou Han drawing: 1.0 mm locating holes (pegs 0.75 mm), pads
# 1.5 mm along the plug axis at KiCad's axial positions. Across the axis the
# drawing puts the pads outside the 6.1 mm body, 3.05-4.65 mm from the axis;
# ours run 2.85-4.85 mm (AS-006; KiCad's ran 2.0-4.5 mm, partly under the
# body). J2 sits 0.3 mm further left than in AS-005 so the tip pad keeps
# 0.45 mm to the right edge (copper-to-edge floor 0.4 mm).
part('J2', 'PJ-320D', 'LOVELACE:Jack_3.5mm_PJ320D_Horizontal_ShouHan',
     W - 5.3, H - 6.22, 90,
     {'S': 'LINE_L', 'T': 'LINE_R', 'R1': 'GND', 'R2': 'GND'},
     'SHOU HAN PJ-320D', kind='connector')

# --- USB entry (bottom-left): ESD, CC, USB-UART ---------------------------
part('U5', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', 5.35, 28.3, 0,
     {1: 'USB_DP', 2: 'GND', 3: 'USB_DM', 4: 'USB_DM', 5: '+5V', 6: 'USB_DP'},
     names={'1': 'IO1', '2': 'GND', '3': 'IO2', '4': 'IO2', '5': 'VBUS',
            '6': 'IO1'}, kind='ic')
C('C23', '100nF', 8.75, 28.75, '+5V')            # beside U5 pin 5 (VBUS ref)
R('R1', '5.1k', 2.2, 39.5, 'CC1', 'GND', rot=90)
R('R2', '5.1k', 8.9, 39.5, 'CC2', 'GND', rot=90)
# CH340N has no DTR: hold the button while plugging in USB to flash.
# V3 = VCC at 3.3 V, one 100 nF serves both pins.
part('U7', 'CH340N', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 15.45, 29.25, 0,
     {1: 'USB_DP', 2: 'USB_DM', 3: 'GND', 5: '+3V3_D', 6: 'UART_RX',
      7: 'UART_TX', 8: '+3V3_D'},
     names={'1': 'UD+', '2': 'UD-', '3': 'GND', '4': 'RTS_N', '5': 'VCC',
            '6': 'TXD', '7': 'RXD', '8': 'V3'}, kind='ic')
C('C24', '100nF', 11.7, 27.6, '+3V3_D', rot=90)

# --- 3.3 V buck (middle); inductor kept >= 15 mm from the DAC ---------------
C('C7', '10uF', 14.5, 27.6, '+5V', big=True)
R('R19', '100k', 18.4, 27.6, '+5V', 'GND')
# 2.0 x 1.6 mm; Murata max 2.1 A at -30 % L, 1.5 A at +40 C rise.
# TPS62162 is a 1 A part.
part('L1', '2.2uH', 'Inductor_SMD:L_Murata_DFE201610P', 18.2, 37.4, 180,
     {1: 'SW', 2: '+3V3_D'}, 'Murata DFE201612P-2R2M', kind='power')
part('U3', 'TPS62162DSGR',
     'Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm_ThermalVias',
     22.0, 37.4, 180,
     {1: 'GND', 2: '+5V', 3: '+5V', 4: 'GND', 5: 'GND', 6: '+3V3_D', 7: 'SW',
      9: 'GND'},
     names={'1': 'PGND', '2': 'VIN', '3': 'EN', '4': 'AGND', '5': 'FB',
            '6': 'VOS', '7': 'SW', '8': 'PG', '9': 'EP_GND'}, kind='power')
C('C4', '10uF', 22.8, 32.9, '+5V', rot=270, big=True)
C('C6', '22uF', 14.6, 36.9, '+3V3_D', big=True)
C('C5', '10uF', 19.25, 36.9, '+3V3_D', mid=True)

# --- eFuse: always on while USB power is present --------------------------
# OVLO 1.2 V * (1 + 383k/100k) = 5.80 V nominal. Worst case with VOV(R)
# 1.183-1.223 V, R13 1 %, R14 0.1 % and +/-0.1 uA pin leakage: 5.63-6.00 V.
# Low end stays above USB-C vSafe5V (5.5 V max); high end reaches the TPS7A20
# recommended VIN max (6.0 V, abs max 6.5 V) and the USBLC6 6 V min breakdown.
part('U6', 'TPS259470ARPWR', 'LOVELACE:TPS25947_RPW0010A', 14.0, 36.6, 0,
     {1: 'POWER_EN', 2: 'OVLO', 5: 'VBUS', 6: '+5V', 7: 'DVDT', 8: 'GND',
      9: 'ILIM'},
     names={'1': 'EN_UVLO', '2': 'OVLO', '3': 'AUXOFF', '4': 'FLT', '5': 'IN',
            '6': 'OUT', '7': 'DVDT', '8': 'GND', '9': 'ILIM', '10': 'ITIMER'},
     kind='power')
C('C21', '100nF', 15.98, 44.0, 'VBUS', mpn='100nF X7R 50V 0402')
R('R13', '383k', 12.75, 39.3, 'VBUS', 'OVLO', mpn='383k 1% 0402')
R('R14', '100k', 12.75, 40.6, 'OVLO', 'GND', mpn='100k 0.1% thin-film 0402')
# ILIM = 3.33 V / R: 5.1 k gives 0.65 A (0.56-0.75 A), a JLC Basic part.
R('R15', '5.1k', 18.75, 40.9, 'ILIM', 'GND')
C('C22', '10nF', 18.75, 42.2, 'DVDT', mpn='10nF X7R 50V 0402')
# EN/UVLO divider: 1.2 V * (1 + 255k/100k) = 4.26 V turn-on.
R('R16', '255k', 20.6, 44.25, 'VBUS', 'POWER_EN')
R('R17', '100k', 18.2, 44.25, 'POWER_EN', 'GND')

# --- Mounting ---------------------------------------------------------------
# One M2 hole in the top-right corner, 11 mm from the antenna end: NPTH, no
# copper within the 5.5 mm head keep-out. Use a nylon screw / standoff here.
HOLES = [(W - 2.75, 2.75)]
for i, (hx, hy) in enumerate(HOLES, 1):
    part(f'H{i}', 'M2', 'MountingHole:MountingHole_2.2mm_M2', hx, hy, 0, {},
         kind='mech')

# Hand-placed: large parts and the DAC / LDO satellites (pin-exact decoupling).
FLOORPLAN = {'U1', 'J1', 'J2', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7', 'L1', 'SW1',
             'D5', 'C25',
             'D2', 'D3', 'C8', 'C9', 'C10', 'C12', 'C13', 'C14', 'C15', 'C16',
             'C17', 'C18', 'R10', 'C1', 'C2', 'C3', 'R5', 'C23'}
if placed:
    for p in parts:
        if p['ref'] in placed['parts'] and p['ref'] not in FLOORPLAN:
            p['x'], p['y'], p['rot'] = placed['parts'][p['ref']]

# --- LCSC / JLCPCB part numbers (stock checked 2026-10-15) ----------------
LCSC_BY_REF = {
    'U1': 'C2973667', 'U2': 'C107671', 'U3': 'C40256', 'U4': 'C2862740',
    'U5': 'C7519', 'U6': 'C3662799', 'U7': 'C2977777', 'J1': 'C165948',
    'J2': 'C431535', 'L1': 'C79317', 'SW1': 'C231329', 'D2': 'C19224',
    'D3': 'C19224', 'D4': 'C12624', 'R13': 'C163468', 'R14': 'C852472',
    'C21': 'C307331', 'D5': 'C8529', 'C25': 'C212684',
}
LCSC_BY_VALUE = {  # (footprint, value) -> JLC basic part where one exists
    (C04, '100nF'): 'C1525', (C04, '1uF'): 'C52923', (C04, '2.2uF'): 'C12530',
    (C04, '10nF'): 'C15195', (C04, '2.2nF'): 'C106861', (C06, '10uF'): 'C19702',
    (C08, '10uF'): 'C15850', (C08, '22uF'): 'C45783', (R04, '10k'): 'C25744',
    (R04, '5.1k'): 'C25905', (R04, '100k'): 'C25741', (R04, '220'): 'C25091',
    (R04, '470'): 'C25117', (R04, '255k'): 'C270623',
}
for p in parts:
    if p['kind'] != 'mech':
        p['lcsc'] = LCSC_BY_REF.get(p['ref']) or LCSC_BY_VALUE[(p['footprint'], p['value'])]

# --- Checker input ----------------------------------------------------------
def centre(p):
    b = p['local_courtyard']
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    a = math.radians(p['rot'])
    return (p['x'] + cx * math.cos(a) + cy * math.sin(a),
            p['y'] - cx * math.sin(a) + cy * math.cos(a))


EDGE_PARTS = ('U1', 'J1', 'J2')
plan = {
    'board': {'w': W, 'h': H, 'edge_clearance': 0.5, 'grid': 0.25,
              'origin': [0, -H], 'id': BOARD_ID, 'rev': BOARD_REV, 'name': NAME},
    # Module courtyard already has 0.31 mm past its castellations; decoupling
    # may sit 0.35 mm from an IC courtyard (SKILL.md section 4).
    'spacing': {'passive-module': 0.5, 'passive-ic': 0.35},
    'zones': {}, 'parts': [], 'near': [], 'apart': [],
    'keepouts': [{'name': f'M2 screw head {i}', 'circle': [x, -y, 2.75],
                  'allow': [f'H{i}']} for i, (x, y) in enumerate(HOLES, 1)],
}
# Pre-routed USB-C escape: D+ join, D- vias and the two VBUS vias sit in the
# 1.6 mm above the pad row (build_pcb.py); parts stay out of it.
J1_ROW = H - 3.65 - 4.045 - .725
# Hand-routed D+ from USBLC6 pin 6 straight across to CH340N UD+ (y = U5 top row).
plan['keepouts'].append({'name': 'USB D+ run U5 -> U7',
                         'rect': [7.2, -27.95, 12.0, -26.75], 'allow': ['U5', 'U7']})
plan['keepouts'].append({'name': 'USB-C escape and VBUS vias',
                         'rect': [2.3, -J1_ROW, 8.9, -(J1_ROW - 1.7)],
                         'allow': ['J1']})
for p in parts:
    x, y = centre(p)
    b = p['local_courtyard']
    plan['parts'].append({
        'ref': p['ref'], 'x': round(x, 5), 'y': round(-y, 5),
        'w': round(b[2] - b[0], 4), 'h': round(b[3] - b[1], 4),
        'rot': p['rot'], 'class': p['kind'],
        'grid': 0.005 if p['ref'] in EDGE_PARTS or p['kind'] == 'mech' else 0.01,
        'locked': p['ref'] in EDGE_PARTS,
        'allow_overhang': p['ref'] in EDGE_PARTS})
NEAR = [
    ('C2', 'U1', 1.0, 'B1 100 nF within 1 mm of module 3V3 pin'),
    ('C3', 'U1', 5.0, 'B1 10 uF within 5 mm'),
    ('C1', 'U1', 3.0, 'EN RC at the EN pin'),
    ('C14', 'U2', 1.0, 'B1 AVDD 100 nF'), ('C10', 'U2', 1.0, 'B1 CPVDD 100 nF'),
    ('C16', 'U2', 1.0, 'B1 DVDD 100 nF'), ('C18', 'U2', 1.0, 'B1 LDOO 100 nF'),
    ('C12', 'U2', 1.0, 'charge-pump flying cap at pins 2/4'),
    ('C13', 'U2', 1.0, 'VNEG cap at pin 5'),
    ('C9', 'U2', 5.0, 'B1 CPVDD / AVDD 10 uF'), ('C15', 'U2', 5.0, 'B1 10 uF'),
    ('C17', 'U2', 5.0, 'B1 10 uF'),
    ('C8', 'U4', 3.0, 'B1 LDO input'), ('C9', 'U4', 3.0, 'B1 LDO output'),
    ('D5', 'U4', 6.0, 'hold-up diode beside the LDO'),
    ('C4', 'U3', 2.0, 'B2 buck input cap'), ('L1', 'U3', 3.0, 'B2 inductor'),
    ('C6', 'L1', 3.0, 'B2 output cap at inductor'),
    ('U5', 'J1', 5.0, 'B9 USB ESD within 5 mm'),
    ('R1', 'J1', 5.0, 'B14 CC termination'), ('R2', 'J1', 5.0, 'B14 CC'),
    ('D2', 'J2', 5.0, 'B9 line-out ESD'), ('D3', 'J2', 5.0, 'B9 line-out ESD'),
    ('C21', 'U6', 1.0, 'B5 eFuse input cap'),
    ('R13', 'U6', 2.0, 'B5 OVLO divider'), ('R14', 'U6', 2.0, 'B5 OVLO'),
    ('R15', 'U6', 2.0, 'B5 ILIM'), ('C22', 'U6', 3.0, 'B5 dVdt'),
    ('C24', 'U7', 1.0, 'B1 CH340 VCC'),
    ('C23', 'U5', 1.5, 'USBLC6 VBUS reference (no load current); D+/D- own both sides'),
]
plan['near'] = [dict(a=a, b=b, max=m, why=w) for a, b, m, w in NEAR]
plan['apart'] = [
    dict(a='L1', b='U2', min=15, why='B15 buck inductor >= 15 mm from DAC'),
    dict(a='U3', b='U2', min=10, why='B15 buck switch node vs DAC analog'),
    dict(a='L1', b='J2', min=5, why='keep SW field off the line-out jack'),
]
(ROOT / 'design.json').write_text(json.dumps(parts, indent=2) + '\n')
(ROOT / 'placement.json').write_text(json.dumps(plan, indent=2) + '\n')
print(len(parts), 'components', f'{W} x {H} mm')
