#!/usr/bin/env python3
"""Check every IC / connector pin against a table written from datasheets.

The expected functions below were written from the vendor datasheets (not
from plan_pcb.py), so a typo in the netlist source shows up here even though
DRC, ERC and parity all agree with it. audit_pcb.py ties design.json to the
board file, so checking design.json covers the board.

  TPS25947 SLVSFC9C Table 5-1      TPS62162 SLVSAM2E Pin Functions
  PCM5102A SLAS859C Pin Functions  TPS7A20 Pin Functions (SOT-23)
  ESP32-WROVER-E datasheet Table 3 USBLC6-2SC6 (ST), CH340N (WCH), HRO
  TYPE-C-31-M-12, JLC/EasyEDA symbols for the last three. PJ-320D:
  Shou Han drawing letters + LCSC engineer's pin functions (2026-10-16).
Run with any Python 3 after plan_pcb.py. Exit 1 on a mismatch.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NC = None  # pin must be left unconnected

# ref -> {pin: expected net}. Nets are this design's names for the function
# the datasheet gives that pin.
EXPECTED = {
    # WROVER-E: 1 GND, 2 3V3, 3 EN, 15/38/39 GND, 25 IO0, 30 IO18, 31 IO19,
    # 33 IO21, 34 RXD0, 35 TXD0, 36 IO22, 37 IO23. Strapping pins IO2 (24),
    # IO12/MTDI (14), IO15/MTDO (23), IO5 (29) stay open on their internal
    # pulls: download mode needs IO2 low, MTDI high would set 1.8 V flash.
    'U1': {'1': 'GND', '2': '+3V3_D', '3': 'EN', '14': NC, '15': 'GND',
           '23': NC, '24': NC, '25': 'BOOT', '29': NC, '30': 'LRCLK',
           '31': 'DATA', '33': 'BCLK', '34': 'UART_RX', '35': 'UART_TX',
           '36': 'XSMT', '37': 'STATUS_GPIO', '38': 'GND', '39': 'GND'},
    # PCM5102A: 1 CPVDD, 2 CAPP, 3 CPGND, 4 CAPM, 5 VNEG, 6 OUTL, 7 OUTR,
    # 8 AVDD, 9 AGND, 10 DEMP, 11 FLT, 12 SCK, 13 BCK, 14 DIN, 15 LRCK,
    # 16 FMT, 17 XSMT, 18 LDOO, 19 DGND, 20 DVDD. DEMP/FLT/FMT low = off,
    # normal filter, I2S; SCK grounded = PLL from BCK.
    'U2': {'1': '+3V3_A', '2': 'CAPP', '3': 'GND', '4': 'CAPM', '5': 'VNEG',
           '6': 'DAC_L', '7': 'DAC_R', '8': '+3V3_A', '9': 'GND', '10': 'GND',
           '11': 'GND', '12': 'GND', '13': 'BCLK', '14': 'DATA',
           '15': 'LRCLK', '16': 'GND', '17': 'XSMT', '18': 'LDOO',
           '19': 'GND', '20': '+3V3_A'},
    # TPS62162 DSG: 1 PGND, 2 VIN, 3 EN, 4 AGND, 5 FB (to AGND on fixed
    # versions), 6 VOS, 7 SW, 8 PG (open drain, unused), EP to AGND.
    'U3': {'1': 'GND', '2': '+5V', '3': '+5V', '4': 'GND', '5': 'GND',
           '6': '+3V3_D', '7': 'SW', '8': NC, '9': 'GND'},
    # TPS7A20 DBV: 1 IN, 2 GND, 3 EN (internal pull-down), 4 NC, 5 OUT.
    'U4': {'1': '+5V_DAC', '2': 'GND', '3': '+5V_DAC', '4': NC,
           '5': '+3V3_A'},
    # USBLC6-2SC6: 1/6 I/O1, 3/4 I/O2 (flow-through pairs), 2 GND, 5 VBUS.
    'U5': {'1': 'USB_DP', '2': 'GND', '3': 'USB_DM', '4': 'USB_DM',
           '5': '+5V', '6': 'USB_DP'},
    # TPS259470A RPW: 1 EN/UVLO, 2 OVLO, 3 AUXOFF (open drain), 4 FLT (open
    # drain), 5 IN, 6 OUT, 7 DVDT, 8 GND, 9 ILM, 10 ITIMER (open = fastest;
    # C26 land to GND, not fitted).
    'U6': {'1': 'POWER_EN', '2': 'OVLO', '3': NC, '4': NC, '5': 'VBUS',
           '6': '+5V', '7': 'DVDT', '8': 'GND', '9': 'ILIM', '10': 'ITIMER'},
    # CH340N: 1 UD+, 2 UD-, 3 GND, 4 RTS# (unused), 5 VCC, 6 TXD, 7 RXD,
    # 8 V3 (tied to VCC for 3.3 V). TXD drives the ESP32 RXD0 and back.
    'U7': {'1': 'USB_DP', '2': 'USB_DM', '3': 'GND', '4': NC, '5': '+3V3_D',
           '6': 'UART_RX', '7': 'UART_TX', '8': '+3V3_D'},
    # USB-C (USB 2.0): D+ A6/B6, D- A7/B7, CC1 A5 / CC2 B5 each with its own
    # 5.1 k Rd, SBU unused.
    'J1': {'A1': 'GND', 'A4': 'VBUS', 'A5': 'CC1', 'A6': 'USB_DP',
           'A7': 'USB_DM', 'A8': NC, 'A9': 'VBUS', 'A12': 'GND', 'B1': 'GND',
           'B4': 'VBUS', 'B5': 'CC2', 'B6': 'USB_DP', 'B7': 'USB_DM',
           'B8': NC, 'B9': 'VBUS', 'B12': 'GND'},
    # RB551V: 1 cathode to the DAC rail, 2 anode from +5V.
    'D5': {'1': '+5V_DAC', '2': '+5V'},
    # KT-0603G: 1 cathode.
    'D4': {'1': 'GND', '2': 'STATUS_A'},
    # T520 polymer tantalum: 1 positive.
    'C25': {'1': '+5V_DAC', '2': 'GND'},
    # Shou Han PJ-320D: drawing terminals A (KiCad S), B (T), C (R1), D (R2);
    # functions from LCSC's engineer: A tip, D ring 1, C ring 2, B sleeve.
    # TRS plug: tip = left, ring = right, sleeve over B + C = ground.
    'J2': {'S': 'LINE_L', 'R2': 'LINE_R', 'R1': 'GND', 'T': 'GND'},
}
# Two-terminal parts whose two nets matter (order free).
PAIRS = {
    'R1': {'CC1', 'GND'}, 'R2': {'CC2', 'GND'}, 'R5': {'+3V3_D', 'EN'},
    'C1': {'EN', 'GND'}, 'R6': {'+3V3_D', 'BOOT'}, 'SW1': {'BOOT', 'GND'},
    'R10': {'XSMT', 'GND'}, 'R13': {'VBUS', 'OVLO'}, 'R14': {'OVLO', 'GND'},
    'R16': {'VBUS', 'POWER_EN'}, 'R17': {'POWER_EN', 'GND'},
    'R15': {'ILIM', 'GND'}, 'C22': {'DVDT', 'GND'}, 'C12': {'CAPP', 'CAPM'},
    'C13': {'VNEG', 'GND'}, 'C18': {'LDOO', 'GND'}, 'L1': {'SW', '+3V3_D'},
    'R11': {'DAC_L', 'LINE_L'}, 'R12': {'DAC_R', 'LINE_R'},
    'R18': {'STATUS_GPIO', 'STATUS_A'},
    'C2': {'+3V3_D', 'GND'}, 'C3': {'+3V3_D', 'GND'},
    'C4': {'+5V', 'GND'}, 'C5': {'+3V3_D', 'GND'},
    'C6': {'+3V3_D', 'GND'}, 'C7': {'+5V', 'GND'},
    'C8': {'+5V_DAC', 'GND'}, 'C9': {'+3V3_A', 'GND'},
    'C10': {'+3V3_A', 'GND'}, 'C14': {'+3V3_A', 'GND'},
    'C15': {'+3V3_A', 'GND'}, 'C16': {'+3V3_A', 'GND'},
    'C17': {'+3V3_A', 'GND'}, 'C19': {'LINE_L', 'GND'},
    'C20': {'LINE_R', 'GND'}, 'C21': {'VBUS', 'GND'},
    'C23': {'+5V', 'GND'}, 'C24': {'+3V3_D', 'GND'},
    'C25': {'+5V_DAC', 'GND'},
    'C26': {'ITIMER', 'GND'},
}
# Values the datasheet equations depend on.
VALUES = {'R13': '383k', 'R14': '100k', 'R16': '255k', 'R17': '100k',
          'R15': '5.1k', 'R1': '5.1k', 'R2': '5.1k', 'R5': '10k', 'C1': '1uF',
          'R10': '10k', 'C22': '10nF', 'L1': '2.2uH', 'C6': '22uF',
          'C18': '100nF', 'C12': '2.2uF', 'C13': '2.2uF', 'R11': '470',
          'R12': '470', 'C19': '2.2nF', 'C20': '2.2nF'}
VALUES.update({
    'C2': '100nF', 'C3': '10uF', 'C4': '10uF', 'C5': '10uF',
    'C7': '10uF', 'C8': '1uF', 'C9': '10uF', 'C10': '100nF',
    'C14': '100nF', 'C15': '10uF', 'C16': '100nF', 'C17': '10uF',
    'C21': '100nF', 'C23': '100nF', 'C24': '100nF',
    'C25': '220uF', 'C26': 'DNP',
})


def check(design):
    if not isinstance(design, list):
        raise ValueError('design must be a list of parts')
    parts = {}
    for part in design:
        if not isinstance(part, dict) or not isinstance(part.get('ref'), str):
            raise ValueError('each part must have a reference')
        ref = part['ref']
        if ref in parts:
            raise ValueError(f'{ref}: duplicate reference')
        if (not isinstance(part.get('nets'), dict)
                or not all(isinstance(k, str) and isinstance(v, str)
                           for k, v in part['nets'].items())
                or not isinstance(part.get('value'), str)
                or not isinstance(part.get('dnp'), bool)):
            raise ValueError(f'{ref}: invalid or missing nets/value/dnp')
        parts[ref] = part

    errors = []
    count = 0

    def expect(ok, message):
        nonlocal count
        count += 1
        if not ok:
            errors.append(message)

    required = EXPECTED.keys() | PAIRS.keys() | VALUES.keys()
    for ref in sorted(required):
        expect(ref in parts, f'{ref}: required part missing')
        if ref in parts:
            want_dnp = ref == 'C26'
            expect(parts[ref]['dnp'] == want_dnp,
                   f'{ref}: expected dnp={want_dnp}, netlist {parts[ref]["dnp"]}')
    for ref, pins in EXPECTED.items():
        if ref in parts:
            for pin, want in pins.items():
                got = parts[ref]['nets'].get(pin)
                expect(got == want,
                       f'{ref} pin {pin}: expected {want}, netlist {got}')
    for ref, want in PAIRS.items():
        if ref in parts:
            got = set(parts[ref]['nets'].values())
            expect(got == want and len(parts[ref]['nets']) == 2,
                   f'{ref}: expected two terminals {sorted(want)}, netlist {sorted(got)}')
    for ref, want in VALUES.items():
        if ref in parts:
            expect(parts[ref]['value'] == want,
                   f'{ref}: expected {want}, netlist {parts[ref]["value"]}')
    for ref, part in parts.items():
        if ref.startswith('C') and ref != 'C12':
            expect('GND' in part['nets'].values(), f'{ref}: no GND terminal')
    return errors, count


def main():
    try:
        errors, count = check(json.loads((ROOT / 'design.json').read_text()))
    except (OSError, ValueError) as exc:
        print(f'MISMATCH {exc}')
        return 1
    print(f'Datasheet pin/passive contracts: {count - len(errors)} / {count} checks match')
    for error in errors:
        print('  MISMATCH', error)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
