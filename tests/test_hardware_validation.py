"""Challenge the real board checkers without KiCad, a network, or hardware."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

BOARD = Path(__file__).resolve().parents[1] / 'hardware/lovelace-as-008'
KICAD_PY = Path('/Volumes/KiCad/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pins = load('pinout_check', BOARD / 'pinout_check.py')
power = load('power_path', BOARD / 'sim/power_path.py')


class PinContractsTest(unittest.TestCase):
    def setUp(self):
        self.design = json.loads((BOARD / 'design.json').read_text())

    def test_baseline(self):
        errors, count = pins.check(self.design)
        self.assertEqual(errors, [])
        self.assertGreater(count, 142)

    def test_original_seven_mutations(self):
        cases = [
            ('U2', 'nets', '16', '+3V3_A'),
            ('U7', 'nets', '6', 'UART_TX'),
            ('R15', 'value', None, '510'),
            ('C25', 'value', None, '22uF'),
            ('C12', 'dnp', None, True),
            ('C15', 'nets', '1', '+3V3_D'),
            ('C17', 'value', None, '10nF'),
        ]
        for ref, key, pin, value in cases:
            with self.subTest(ref=ref):
                design = copy.deepcopy(self.design)
                part = next(p for p in design if p['ref'] == ref)
                if pin:
                    part[key][pin] = value
                else:
                    part[key] = value
                errors, _ = pins.check(design)
                self.assertTrue(any(ref in error for error in errors), errors)

    def test_required_caps_cannot_be_dnp_or_on_wrong_rail(self):
        for ref in ('C4', 'C5', 'C6', 'C7', 'C9', 'C12', 'C13', 'C15', 'C17', 'C25'):
            for key, value in [('dnp', True), ('nets', {'1': 'WRONG', '2': 'GND'})]:
                with self.subTest(ref=ref, key=key):
                    design = copy.deepcopy(self.design)
                    next(p for p in design if p['ref'] == ref)[key] = value
                    self.assertTrue(any(ref in e for e in pins.check(design)[0]))

    def test_polarity_and_intentional_dnp(self):
        for ref, key, value in [('C25', 'nets', {'1': 'GND', '2': '+5V_DAC'}),
                                ('C26', 'dnp', False)]:
            with self.subTest(ref=ref):
                design = copy.deepcopy(self.design)
                next(p for p in design if p['ref'] == ref)[key] = value
                self.assertTrue(any(ref in e for e in pins.check(design)[0]))

    def test_missing_duplicate_and_malformed_parts(self):
        missing = [p for p in self.design if p['ref'] != 'C12']
        self.assertIn('C12: required part missing', pins.check(missing)[0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            pins.check(self.design + [self.design[0]])
        for field in ('value', 'nets', 'dnp'):
            with self.subTest(field=field):
                design = copy.deepcopy(self.design)
                del next(p for p in design if p['ref'] == 'C12')[field]
                with self.assertRaisesRegex(ValueError, 'C12'):
                    pins.check(design)


@unittest.skipUnless(KICAD_PY.is_file(), 'KiCad Python required for saved-PCB mutations')
class BoardReadbackTest(unittest.TestCase):
    def test_wrong_saved_value_and_dnp_are_rejected(self):
        script = '''
import pathlib, runpy, sys
from unittest.mock import patch
import pcbnew
board_dir = pathlib.Path(sys.argv[1])
board = pcbnew.LoadBoard(str(board_dir / 'lovelace-as-008.kicad_pcb'))
ref, field = sys.argv[2:]
part = next(f for f in board.GetFootprints() if f.GetReference() == ref)
if field == 'value':
    part.SetValue('22uF')
else:
    part.SetDNP(True)
with patch.object(pcbnew, 'LoadBoard', return_value=board):
    try:
        runpy.run_path(str(board_dir / 'audit_pcb.py'), run_name='__main__')
    except AssertionError as exc:
        print(exc)
        assert ref in str(exc)
    else:
        raise SystemExit('Wrong saved-PCB data was accepted')
'''
        for ref, field in [('C25', 'value'), ('C12', 'dnp')]:
            with self.subTest(ref=ref, field=field):
                result = subprocess.run([str(KICAD_PY), '-c', script, str(BOARD), ref, field],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'{ref}: PCB', result.stdout)


class PowerRunnerTest(unittest.TestCase):
    def run_with(self, stdout, stderr='', returncode=0, error=None):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(power, 'ROOT', Path(directory)), patch.object(
                    power.subprocess, 'run', side_effect=error,
                    return_value=types.SimpleNamespace(
                        stdout=stdout, stderr=stderr, returncode=returncode)):
                return power.run('test', 'meas tran voltage min v(a3)',
                                 vin=5, rsrc=.1, ilim=.654, eff=.85,
                                 ibase=.08, ipk=0, pw='1m', per='2m', tstop=.15)

    def test_complete_analysis(self):
        self.assertEqual(self.run_with('voltage = 3.3\nend_time = 1.5e-1')['voltage'], 3.3)

    def test_exit_zero_and_partial_measurements_are_not_pass(self):
        for stdout, stderr, code in [
                ('voltage = 3.3\nend_time = 0.000054', '', 0),
                ('voltage = 3.3', '', 0),
                ('end_time = .15', '', 0),
                ('voltage = nan\nend_time = .15', '', 0),
                ('voltage = inf\nend_time = .15', '', 0),
                ('voltage = 3.3\nend_time = .15', 'doAnalyses: TRAN: Timestep too small', 0),
                ('voltage = 3.3\nend_time = .15', 'Error: simulation aborted', 0),
                ('voltage = 3.3\nend_time = .15', '', 1)]:
            with self.subTest(stdout=stdout, stderr=stderr, code=code):
                with self.assertRaises(power.SimulationError):
                    self.run_with(stdout, stderr, code)

    def test_timeout_and_missing_executable(self):
        for error in (subprocess.TimeoutExpired('ngspice', 30), FileNotFoundError('ngspice')):
            with self.subTest(error=error):
                with self.assertRaises(power.SimulationError):
                    self.run_with('', error=error)

    def test_shutdown_paths(self):
        self.assertEqual(power.mute_time_ms('clock_stop'), 3)
        self.assertAlmostEqual(power.mute_time_ms('xsmt', 44100), 3.601360544)
        self.assertAlmostEqual(power.mute_time_ms('xsmt', 48000), 3.325)

    def test_incomplete_run_writes_unverified_report(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(power, 'ROOT', Path(directory)), patch.object(
                    power, 'run', side_effect=power.SimulationError('incomplete')), patch('builtins.print'):
                self.assertEqual(power.main(), 2)
                report = json.loads((Path(directory) / 'reports/sim.json').read_text())
        self.assertEqual(report['status'], 'UNVERIFIED')
        self.assertEqual(len(report['execution_errors']), 55)
        self.assertEqual(len(report['holdup']), 16)

    def test_clock_stop_uses_3p1_voltage_and_keeps_xsmt_unverified(self):
        for margin_ms, expected_exit, status in [(3.001, 0, 'PASS'), (2.999, 1, 'FAIL')]:
            with self.subTest(margin_ms=margin_ms), tempfile.TemporaryDirectory() as directory:
                row = dict(t_limit=0, d3_min=3.3, t_esp_off=.101,
                           t_dac_off=.101 + margin_ms / 1000,
                           t_dac_3p2=.103, t_dac_3p0=.106)
                with patch.object(power, 'ROOT', Path(directory)), patch.object(
                        power, 'run', side_effect=lambda *args, **kwargs: dict(row)), patch('builtins.print'):
                    self.assertEqual(power.main(), expected_exit)
                report = json.loads((Path(directory) / 'reports/sim.json').read_text())
                self.assertEqual(report['status'], status)
                self.assertEqual(len(report['holdup']), 16)
                self.assertTrue(all(r['status'] == status for r in report['holdup']))
                self.assertEqual(report['xsmt']['status'], 'UNVERIFIED')


class ReleaseGuardTest(unittest.TestCase):
    def test_real_build_stops_before_board_and_release_on_failed_checks(self):
        for bad_pin, sim_exit in [(True, 0), (False, 1), (False, 2)]:
            with self.subTest(bad_pin=bad_pin, sim_exit=sim_exit), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'make_board.sh').write_bytes((BOARD / 'make_board.sh').read_bytes())
                (root / 'pinout_check.py').write_bytes((BOARD / 'pinout_check.py').read_bytes())
                design = json.loads((BOARD / 'design.json').read_text())
                if bad_pin:
                    next(p for p in design if p['ref'] == 'C12')['dnp'] = True
                (root / 'design.json').write_text(json.dumps(design))
                (root / 'sim').mkdir()
                (root / 'sim/power_path.py').write_text(f'raise SystemExit({sim_exit})\n')
                (root / 'release').mkdir()
                (root / 'release/old').write_text('previous release')
                runtime = root / 'kicad/Frameworks/Python.framework/Versions/Current/bin'
                runtime.mkdir(parents=True)
                # Skip generation/placement only; run the production pin and power commands.
                wrapper = ('#!/bin/sh\ncase "$1" in\n'
                           'plan_pcb.py|*/placement_check.py) exit 0;;\n'
                           'build_pcb.py) touch board-generation-reached; exit 9;;\n'
                           f'esac\nexec {shlex.quote(sys.executable)} "$@"\n')
                for path in (runtime / 'python3', root / 'python3'):
                    path.write_text(wrapper)
                    path.chmod(0o755)
                env = dict(os.environ, KICAD=str(root / 'kicad'),
                           PATH=str(root) + os.pathsep + os.environ['PATH'])
                result = subprocess.run(['bash', str(root / 'make_board.sh')],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 1 if bad_pin else sim_exit, result.stdout + result.stderr)
                self.assertFalse((root / 'board-generation-reached').exists())
                self.assertEqual((root / 'release/old').read_text(), 'previous release')
