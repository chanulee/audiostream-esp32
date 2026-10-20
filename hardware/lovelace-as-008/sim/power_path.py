#!/usr/bin/env python3
"""Behavioural ngspice model of the LOVELACE power path.

USB source + cable -> TPS259470A eFuse -> +5V -> TPS62162 buck -> +3V3_D
(ESP32 load) and +5V -> RB551V -> +5V_DAC (C25 hold-up) -> TPS7A2033 -> DAC.

The parts are datasheet-level behavioural blocks, not vendor models:
  eFuse   UVLO 1.2 V x (1 + 255k/100k) on, 1.09 V x (...) off; OVLO likewise,
          output slew 2000 / CdVdt(pF) V/ms (SLVSFC9C eq. 4) = 0.2 V/ms,
          RON 30 mOhm, active current limit at ILIM (ITIMER open), true
          reverse current blocking.
  buck    ideal source: Vout = min(3.3, 0.98 x VIN), input power = Pout / eff.
  LDO     Vout = min(3.3, VIN - 20 mV), input current = output current.
  ESP32   current pulses on +3V3_D after the EN RC (10k / 1 uF); peak from
          the WROVER-E datasheet table 16 (350 mA, 802.11b 19.5 dBm).
Capacitors carry DC-bias derating at their working voltage. Parasitics of the
real layout, buck loop dynamics and the eFuse foldback are not modelled.

Run with any Python 3 and ngspice on PATH. Writes ../reports/sim.json and
raw inputs/logs to ../reports/sim-cases/. Exit 1 on a criterion failure,
2 on an incomplete/unusable simulation. XSMT timing is not simulated.
"""
import json
import math
import re
import subprocess
import sys
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
C25 p5d n25 {cap_uF}u
R25 n25 0 25m
C8 p5d 0 1u
* LDO -> +3V3_A, DAC 31 mA, C9/C15/C17 (10 uF 0603 at 3.3 V ~ 5 uF each)
Bldo a3x 0 V = max(0, min(3.3, V(p5d)-0.02))
Vla a3x a3 0
Ca3 a3 0 15u
Rdac a3 0 {dac_ohm}
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


class SimulationError(RuntimeError):
    """The simulator did not produce a complete, usable transient analysis."""


def run(name, meas, **p):
    p.setdefault('tun', 1)
    p.setdefault('tstop', 0.12)
    p.setdefault('cap_uF', 220)
    p.setdefault('dac_ohm', 106)
    required = set(re.findall(r'^meas tran (\w+)', meas, re.M)) | {'end_time'}
    net = NETLIST.format(meas=meas + '\nmeas tran end_time max time', **p)
    artifacts = ROOT / 'reports' / 'sim-cases'
    artifacts.mkdir(parents=True, exist_ok=True)
    circuit = artifacts / f'{name}.cir'
    log = artifacts / f'{name}.log'
    circuit.write_text(net)
    try:
        proc = subprocess.run(['ngspice', '-b', str(circuit)], capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write_text(f'{exc}\nstdout: {getattr(exc, "stdout", None)!r}\n'
                       f'stderr: {getattr(exc, "stderr", None)!r}\n')
        raise SimulationError(f'{name}: {exc}; see {log}') from exc
    out = proc.stdout + '\n' + proc.stderr
    log.write_text(out)
    if (proc.returncode != 0 or re.search(
            r'\b(error|fatal|aborted)\b|timestep too small|singular matrix|simulation interrupted',
            out, re.I)):
        raise SimulationError(f'{name}: simulator error (exit {proc.returncode}); see {log}')
    res = {}
    for key, value in re.findall(r'^\s*(\w+)\s*=\s*(\S+)', out, re.M):
        if key in required:
            try:
                res[key] = float(value)
            except ValueError:
                pass
    invalid = sorted(key for key in required if key not in res or not math.isfinite(res[key]))
    if invalid:
        raise SimulationError(f'{name}: missing/nonfinite measurements {invalid}; see {log}')
    if abs(res['end_time'] - p['tstop']) > 1e-9:
        raise SimulationError(f'{name}: stopped at {res["end_time"]}, expected {p["tstop"]}; see {log}')
    return res


def mute_time_ms(path, sample_rate=44100):
    # PCM5102A SLAS859C 11.2: these are two different shutdown paths.
    if path == 'clock_stop':
        return 3.0
    if path == 'xsmt' and sample_rate > 0:
        return 150000 / sample_rate + 0.2
    raise ValueError('unknown mute path or invalid sample rate')


START = """meas tran t_p5 when v(p5)={p5_on} rise=1
meas tran t_p5d when v(p5d)=4.0 rise=1
meas tran t_d3 when v(d3)=3.2 rise=1
meas tran t_esp when v(act)=0.5 rise=1
meas tran i_max max v(imon) from=0 to=0.1
meas tran t_limit integ v(cl) from=0.001 to=0.1
meas tran d3_min min v(d3) from=0.06 to=0.1"""
PULSE = """meas tran p5_min min v(p5) from=0.06 to=0.12
meas tran p5d_min min v(p5d) from=0.06 to=0.12
meas tran d3_min min v(d3) from=0.06 to=0.12
meas tran a3_min min v(a3) from=0.06 to=0.12
meas tran i_max max v(imon) from=0.06 to=0.12
meas tran t_limit integ v(cl) from=0.06 to=0.12"""
# Brownout is only an assumed clock-stop event, not a measured BCK edge.
# All DAC supplies share a3: DVDD/CPVDD need >=3.1 V (SLAS859C 8.3).
HOLD = """meas tran t_esp_off when v(d3)=2.43 fall=1 td=0.1
meas tran t_dac_3p2 when v(a3)=3.2 fall=1 td=0.1
meas tran t_dac_off when v(a3)=3.1 fall=1 td=0.1
meas tran t_dac_3p0 when v(a3)=3.0 fall=1 td=0.1
meas tran t_c25 when v(p5d)=3.35 fall=1 td=0.1"""


def main():
    results = {
        'status': 'UNVERIFIED',
        'scope': 'Behavioral power-path model, not switching-loop or physical-board validation',
        'assumptions': ['Ideal buck; fixed 20 mV LDO dropout; resistive DAC load',
                        'ESP brownout at 2.43 V is assumed to stop I2S',
                        '45 mA is a 25 C datasheet condition, not an all-temperature bound'],
        'xsmt': {'status': 'UNVERIFIED',
                 'required_ms': {str(fs): mute_time_ms('xsmt', fs) for fs in (44100, 48000)},
                 'reason': 'No XSMT waveform or DAC mute behavior in this model; measure on hardware'},
        'startup': [], 'pulsed': [], 'holdup': [],
        'failures': [], 'execution_errors': [],
    }

    def measure(group, name, meas, **params):
        try:
            row = run(name, meas, **params)
        except SimulationError as exc:
            results['execution_errors'].append(str(exc))
            row = {'status': 'UNVERIFIED', 'error': str(exc)}
        row['case'] = name
        results[group].append(row)
        return row

    for vin, rsrc, ilim in [(5.0, .1, .556), (4.4, .3, .556), (5.0, .1, .654)]:
        r = measure('startup', f'startup-{vin}-{ilim}',
                    START.format(p5_on=round(.9 * vin, 3)), vin=vin, rsrc=rsrc,
                    ilim=ilim, eff=.8, ibase=.115, ipk=.255,
                    pw='1m', per='2m', tstop=.1)
        r.update(vin=vin, rsrc=rsrc, ilim=ilim)
        if r.get('status') != 'UNVERIFIED':
            r['status'] = 'PASS' if r['t_limit'] <= 1e-4 and r['d3_min'] >= 3.2 else 'FAIL'
            if r['status'] == 'FAIL':
                results['failures'].append(r['case'])
        print(f"{r['case']}: {r['status']}", flush=True)

    for vin, rsrc in [(5.0, .1), (4.75, .2), (4.4, .3)]:
        for ilim in (.556, .654):
            for peak in (.37, .5, .6, .7, .8, .9):
                r = measure('pulsed', f'pulsed-{vin}-{ilim}-{peak}', PULSE,
                            vin=vin, rsrc=rsrc, ilim=ilim, eff=.8,
                            ibase=.115, ipk=round(peak - .115, 3), pw='1m', per='2m')
                r.update(vin=vin, rsrc=rsrc, ilim=ilim, peak_3v3=peak)
                if r.get('status') != 'UNVERIFIED':
                    # Higher peaks deliberately probe overload, not required operating points.
                    r['status'] = ('PASS' if r['t_limit'] <= 0 and r['d3_min'] >= 3.2
                                   else 'FAIL') if peak <= .37 else 'STRESS_ONLY'
                    if r['status'] == 'FAIL':
                        results['failures'].append(r['case'])
                print(f"{r['case']}: {r['status']}", flush=True)

    for vin, rsrc in [(5.0, .1), (4.4, .3)]:
        for load in (.08, .25):
            for cap, current in ((220, 31), (176, 31), (220, 45), (176, 45)):
                r = measure('holdup', f'hold-{vin}-{load}-{cap}-{current}', HOLD,
                            vin=vin, rsrc=rsrc, ilim=.654, eff=.85,
                            ibase=load, ipk=0, pw='1m', per='2m', tun=.1, tstop=.15,
                            cap_uF=cap, dac_ohm=3.3 / (current / 1000))
                r.update(vin=vin, rsrc=rsrc, esp_load=load, cap_uF=cap, dac_mA=current)
                if r.get('status') != 'UNVERIFIED':
                    r['margin_ms'] = (r['t_dac_off'] - r['t_esp_off']) * 1000
                    r['margin_3p2_ms'] = (r['t_dac_3p2'] - r['t_esp_off']) * 1000
                    r['margin_3p0_ms'] = (r['t_dac_3p0'] - r['t_esp_off']) * 1000
                    r['required_clock_stop_ms'] = mute_time_ms('clock_stop')
                    r['status'] = 'PASS' if r['margin_ms'] >= r['required_clock_stop_ms'] else 'FAIL'
                    if r['status'] == 'FAIL':
                        results['failures'].append(r['case'])
                    print(f"{r['case']}: {r['status']} {r['margin_ms']:.3f} ms to 3.1 V (need 3.000)", flush=True)
                else:
                    print(f"{r['case']}: UNVERIFIED", flush=True)

    results['status'] = ('UNVERIFIED' if results['execution_errors'] else
                         'FAIL' if results['failures'] else 'PASS')
    report = ROOT / 'reports' / 'sim.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
    print(f"Behavioral model: {results['status']}; XSMT and switching response: UNVERIFIED")
    for error in results['execution_errors']:
        print(error)
    return 2 if results['execution_errors'] else 1 if results['failures'] else 0


if __name__ == '__main__':
    sys.exit(main())
