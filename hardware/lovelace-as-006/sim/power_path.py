#!/usr/bin/env python3
"""Behavioural ngspice model of the LOVELACE power path.

USB source + cable -> TPS259470A eFuse -> +5V -> TPS62162 buck -> +3V3_D
(ESP32 load) and +5V -> RB551V -> +5V_DAC (C25 hold-up) -> TPS7A2033 -> DAC.

The parts are datasheet-level behavioural blocks, not vendor models:
  eFuse   UVLO 1.2 V x (1 + 255k/100k) on, 1.09 V x (...) off; OVLO likewise,
          output slew 2000 / CdVdt(pF) V/ms (SLVSFC9C eq. 4) = 0.2 V/ms,
          RON 30 mOhm, active current limit at ILIM (ITIMER open), true
          reverse current blocking.
  buck    averaged: Vout = min(3.3, 0.98 x VIN), input power = Pout / eff.
  LDO     Vout = min(3.3, VIN - 20 mV), input current = output current.
  ESP32   current pulses on +3V3_D after the EN RC (10k / 1 uF); peak from
          the WROVER-E datasheet table 16 (350 mA, 802.11b 19.5 dBm).
Capacitors carry DC-bias derating at their working voltage. Parasitics of the
real layout, buck loop dynamics and the eFuse foldback are not modelled.

Run with any Python 3 and ngspice on PATH. Writes ../reports/sim.json and
prints a summary. Exit 1 if a pass criterion fails.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NETLIST = """* LOVELACE power path
.param ilim={ilim} eff={eff} vin={vin} rsrc={rsrc} tun={tun}
.param ibase={ibase} ipk={ipk} pw={pw} per={per}
* USB source, cable, unplug at tun
Vch ch 0 PWL(0 0 2u {{vin}})
Vctl ctl 0 PWL(0 1 {{tun}} 1 {{tun+1u}} 0)
S1 ch c1 ctl 0 swc
.model swc sw vt=0.5 vh=0.01 ron={{rsrc}} roff=1e9
Lc c1 vbus 0.5u
Rlc c1 vbus 2
C21 vbus 0 100n
R13 vbus ovlo 383k
R14 ovlo 0 100k
R16 vbus en 255k
R17 en 0 100k
* eFuse
* UVLO / OVLO comparators with the datasheet hysteresis (rise 1.20 V,
* fall 1.09 V): uv = 1 while enabled, ov = 1 while over-voltage
Buv uvx 0 V = 0.5*(1+tanh((V(en)-1.2+0.11*V(uv))/0.003))
Ruv uvx uv 1k
Cuv uv 0 1n
Bov ovx 0 V = 0.5*(1+tanh((V(ovlo)-1.2+0.11*V(ov))/0.003))
Rov ovx ov 1k
Cov ov 0 1n
Bon on 0 V = V(uv)*(1-V(ov))
Cramp ramp 0 1m
Bramp 0 ramp I = 1m*(V(on)*200*0.5*(1+tanh((V(vbus)+0.3-V(ramp))/0.02)) - (1-V(on))*V(ramp)*1000)
Bdem dem 0 V = (min(V(ramp),V(vbus))-V(p5))/0.03
Bief vbus p5 I = V(on)*min({{ilim}}, max(0, V(dem)))
Bmon imon 0 V = V(on)*min({{ilim}}, max(0, V(dem)))
Bcl cl 0 V = 0.5*(1+tanh((V(dem)-{{ilim}})/0.005))
* +5V: C4, C7 (10 uF 25 V 0805 at 5 V ~ 7 uF), C23, bleeder R19
C4 p5 n4 7u
R4 n4 0 5m
C7 p5 n7 7u
R7 n7 0 5m
C23 p5 0 100n
R19 p5 0 100k
* hold-up diode and C25
D5 p5 p5d dsch
.model dsch D(IS=1e-5 N=1.2 RS=0.15 CJO=30p)
C25 p5d n25 220u
R25 n25 0 25m
C8 p5d 0 1u
* LDO -> +3V3_A, DAC 31 mA, C9/C15/C17 (10 uF 0603 at 3.3 V ~ 5 uF each)
Bldo a3x 0 V = max(0, min(3.3, V(p5d)-0.02))
Vla a3x a3 0
Ca3 a3 0 15u
Rdac a3 0 106
Bldoin p5d 0 I = I(Vla)
* buck -> +3V3_D
Bbon bon 0 V = 0.5*(1+tanh((V(p5)-3.0)/0.05))
Bbk d3x 0 V = V(bon)*min(3.3, V(p5)*0.98)
Vbs d3x d3y 0
Rbk d3y d3 20m
Bbkin p5 0 I = V(d3x)*max(0,I(Vbs))/({{eff}}*max(V(p5),1))
* C6 22 uF 0805 ~ 14 uF, C5 / C3 10 uF 0603 ~ 5 uF each (module caps ignored)
C6 d3 n6 14u
R6 n6 0 3m
C35 d3 0 10u
* EN RC and ESP32 load (+ CH340N and LED in the base current)
R5 d3 ene 10k
C1 ene 0 0.8u
Bact act 0 V = 0.5*(1+tanh((V(ene)-2.2)/0.05))
Vp pulse 0 PULSE(0 1 0 1u 1u {{pw}} {{per}})
Bload d3 0 I = V(act)*({{ibase}}+{{ipk}}*V(pulse))*min(1, max(V(d3),0)/2.5)
.options method=gear reltol=1e-4 abstol=1e-9 itl4=100
.tran 5u {tstop} 0 5u
.control
run
{meas}
quit
.endc
.end
"""


def run(name, meas, **p):
    p.setdefault('tun', 1)            # no unplug unless asked
    p.setdefault('tstop', 0.12)
    net = NETLIST.format(meas=meas, **p)
    with tempfile.NamedTemporaryFile('w', suffix='.cir', delete=False) as f:
        f.write(net)
    out = subprocess.run(['ngspice', '-b', f.name], capture_output=True,
                         text=True).stdout
    res = {}
    for line in out.splitlines():
        m = re.match(r'\s*(\w+)\s*=\s*([-+0-9.eE]+)', line)
        if m:
            res[m.group(1)] = float(m.group(2))
    if not res:
        raise SystemExit(f'{name}: ngspice produced no results\n{out[-2000:]}')
    return res


results = {'startup': [], 'pulsed': [], 'holdup': []}
fail = []

# 1. Start-up: hot plug at t = 0, ESP32 boots and calibrates RF at full TX.
START = """meas tran t_p5 when v(p5)={p5_on} rise=1
meas tran t_p5d when v(p5d)=4.0 rise=1
meas tran t_d3 when v(d3)=3.2 rise=1
meas tran t_esp when v(act)=0.5 rise=1
meas tran i_max max v(imon) from=0 to=0.1
meas tran t_limit integ v(cl) from=0.001 to=0.1
meas tran d3_min min v(d3) from=0.06 to=0.1"""
for vin, rsrc, ilim in [(5.0, .1, .556), (4.4, .3, .556), (5.0, .1, .654)]:
    r = run('startup', START.format(p5_on=round(.9 * vin, 3)), vin=vin, rsrc=rsrc, ilim=ilim, eff=.8,
            ibase=.115, ipk=.255, pw='1m', per='2m', tstop=.1)
    r.update(vin=vin, rsrc=rsrc, ilim=ilim)
    results['startup'].append(r)
    if r['t_limit'] > 1e-4 or r['d3_min'] < 3.2:
        fail.append(f'startup {vin} V / ILIM {ilim}: {r}')

# 2. Pulsed ESP32 load after start-up (window 60-120 ms): 3V3 peak current
# swept from the datasheet peak (0.37 A incl. CH340N / LED) upwards.
PULSE = """meas tran p5_min min v(p5) from=0.06 to=0.12
meas tran p5d_min min v(p5d) from=0.06 to=0.12
meas tran d3_min min v(d3) from=0.06 to=0.12
meas tran a3_min min v(a3) from=0.06 to=0.12
meas tran i_max max v(imon) from=0.06 to=0.12
meas tran t_limit integ v(cl) from=0.06 to=0.12"""
for vin, rsrc in [(5.0, .1), (4.75, .2), (4.4, .3)]:
    for ilim in (.556, .654):
        for peak in (.37, .5, .6, .7, .8, .9):
            r = run('pulsed', PULSE, vin=vin, rsrc=rsrc, ilim=ilim, eff=.8,
                    ibase=.115, ipk=round(peak - .115, 3), pw='1m', per='2m')
            r.update(vin=vin, rsrc=rsrc, ilim=ilim, peak_3v3=peak)
            results['pulsed'].append(r)
            if peak <= .37 and (r['t_limit'] > 0 or r['d3_min'] < 3.2):
                fail.append(f'pulsed {vin} V / ILIM {ilim} / {peak} A: {r}')

# 3. Hold-up: USB pulled at 100 ms while playing. ESP32 stops its I2S clock
# at brown-out (2.43 V); the DAC must stay powered 3.6 ms longer to finish its
# clock-loss soft mute (PCM5102A 11.2: 150 samples + 0.2 ms at 44.1 kHz).
HOLD = """meas tran t_esp_off when v(d3)=2.43 fall=1 td=0.1
meas tran t_dac_off when v(a3)=3.2 fall=1 td=0.1
meas tran t_c25 when v(p5d)=3.35 fall=1 td=0.1"""
for vin, rsrc in [(5.0, .1), (4.4, .3)]:
    for load in (.08, .25):
        r = run('holdup', HOLD, vin=vin, rsrc=rsrc, ilim=.654, eff=.85,
                ibase=load, ipk=0, pw='1m', per='2m', tun=.1, tstop=.15)
        r.update(vin=vin, rsrc=rsrc, esp_load=load,
                 margin_ms=round((r['t_dac_off'] - r['t_esp_off']) * 1e3, 2))
        results['holdup'].append(r)
        if r['margin_ms'] < 3.6:
            fail.append(f'holdup {vin} V / {load} A: margin {r["margin_ms"]} ms')

(ROOT / 'reports' / 'sim.json').write_text(json.dumps(results, indent=1) + '\n')

print('Start-up (hot plug, RF calibration at full TX):')
for r in results['startup']:
    print(f"  {r['vin']} V/{r['rsrc']} ohm ILIM {r['ilim']} A: +5V 90% at "
          f"{r['t_p5']*1e3:.1f} ms, +5V_DAC 4.0 V at {r['t_p5d']*1e3:.1f} ms, "
          f"3V3 at {r['t_d3']*1e3:.1f} ms, ESP32 on at {r['t_esp']*1e3:.1f} ms; "
          f"eFuse max {r['i_max']*1e3:.0f} mA, in limit {r['t_limit']*1e3:.2f} ms")
print('Pulsed load (1 ms on / 1 ms off), worst case per row:')
for r in results['pulsed']:
    print(f"  {r['vin']} V ILIM {r['ilim']} A peak {r['peak_3v3']} A: "
          f"+5V min {r['p5_min']:.2f} V, 3V3 min {r['d3_min']:.2f} V, "
          f"3V3A min {r['a3_min']:.2f} V, eFuse max {r['i_max']*1e3:.0f} mA, "
          f"in limit {r['t_limit']*1e3:.2f} ms")
print('Hold-up on unplug:')
for r in results['holdup']:
    print(f"  {r['vin']} V ESP32 {r['esp_load']} A: ESP32 off "
          f"{(r['t_esp_off']-.1)*1e3:.1f} ms, DAC off "
          f"{(r['t_dac_off']-.1)*1e3:.1f} ms after unplug, margin "
          f"{r['margin_ms']} ms (need 3.6)")
print('FAIL' if fail else 'PASS', *fail, sep='\n  ')
sys.exit(1 if fail else 0)
