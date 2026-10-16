"""Run with KiCad Python: unittest discover -s tests -p test_silkscreen.py."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from silkscreen_editor import KICAD, check_layout, current_board, revision, save_layout
BOARD = current_board()[0]
sys.path.insert(0, str(BOARD.parent))
from silkscreen import apply_layout, apply_saved, read_layout, validate


def example(side='B.SilkS'):
    return dict(version=1, items=[dict(id='logo', kind='svg', side=side, svg='<svg/>',
                x=8, y=12, width=4, height=2, rotation=90,
                rectangles=[[0, 0, .25, 1], [.75, 0, .25, 1]])])


class ValidationTest(unittest.TestCase):
    def test_multiline_text_allows_newlines_but_not_other_controls(self):
        layout = example()
        layout['items'][0].update(kind='text', text='5V ONLY\n4.75-5.25V', size=.8, thickness=.15)
        validate(layout, 37, 41)
        for control in ('\t', '\r', '\0'):
            layout['items'][0]['text'] = '5V' + control
            with self.assertRaises(ValueError):
                validate(layout, 37, 41)

    def test_invalid_layers_numbers_and_artwork(self):
        for key, value in [('side', 'B.Cu'), ('x', float('nan')), ('x', True), ('rotation', 999),
                           ('rectangles', [[0, 0, 2, 1]]), ('x', .1)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                layout = example()
                layout['items'][0][key] = value
                validate(layout, 37, 41)

    def test_duplicates_and_payload_shapes(self):
        layout = example()
        layout['items'].append(copy.deepcopy(layout['items'][0]))
        for bad in [layout, None, {'version': 1, 'items': [None]}]:
            with self.assertRaises(ValueError):
                validate(bad, 37, 41)


@unittest.skipUnless(importlib.util.find_spec('pcbnew'), 'KiCad Python required')
class BoardTest(unittest.TestCase):
    def test_cleared_text_is_saved_but_not_printed(self):
        layout = example()
        layout['items'][0].update(kind='text', text='', size=.8, thickness=.15)
        blank = copy.deepcopy(layout['items'][0])
        blank.update(id='whitespace', text=' \n ')
        layout['items'].append(blank)
        save_layout(self.path, layout, revision(self.path, self.directory / 'silkscreen.json'), 37, 41)
        board = self.p.LoadBoard(str(self.path))
        self.assertEqual(read_layout(board, self.directory, 37, 41), layout)
        self.assertFalse(any(isinstance(g, self.p.PCB_TEXT) for g in board.GetDrawings()))

    def test_multiline_text_survives_save_and_reload(self):
        layout = example()
        layout['items'][0].update(kind='text', text='BUTTON\n1x: PLAY / PAUSE\n\nHOLD: PAIR', size=.8, thickness=.15)
        save_layout(self.path, layout, revision(self.path, self.directory / 'silkscreen.json'), 37, 41)
        board = self.p.LoadBoard(str(self.path))
        text = next(g for g in board.GetDrawings() if isinstance(g, self.p.PCB_TEXT))
        self.assertEqual(text.GetText(), layout['items'][0]['text'])
        self.assertEqual(read_layout(board, self.directory, 37, 41), layout)

    def setUp(self):
        import pcbnew as p
        self.p = p
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / BOARD.name
        shutil.copy2(BOARD, self.path)
        # Migration tests start from native text, independent of the user's SVG artwork.
        board = p.LoadBoard(str(self.path))
        for drawing in list(board.GetDrawings()):
            if drawing.GetLayer() in (p.F_SilkS, p.B_SilkS) and not isinstance(drawing, p.PCB_TEXT):
                board.Delete(drawing)
        p.SaveBoard(str(self.path), board)

    def fingerprint(self, board):
        # Copper, connectivity, footprints, holes, planes and footprint markings.
        return (sorted((t.m_Uuid.AsString(), t.GetStart().x, t.GetStart().y, t.GetEnd().x,
                        t.GetEnd().y, t.GetWidth(t.GetLayer()) if isinstance(t, self.p.PCB_VIA) else t.GetWidth(),
                        t.GetLayer(), t.GetNetname()) for t in board.GetTracks()),
                sorted((f.GetReference(), f.GetPosition().x, f.GetPosition().y,
                        f.GetOrientationDegrees(), tuple(sorted((a.GetNumber(), a.GetNetname()) for a in f.Pads())),
                        tuple(sorted(g.m_Uuid.AsString() for g in f.GraphicalItems()))) for f in board.GetFootprints()),
                sorted(z.m_Uuid.AsString() for z in board.Zones()),
                sorted(g.m_Uuid.AsString() for g in board.GetDrawings() if g.GetLayer() not in (self.p.F_SilkS, self.p.B_SilkS)))

    def test_existing_text_round_trip_and_regeneration(self):
        board = self.p.LoadBoard(str(self.path))
        before = self.fingerprint(board)
        expected = sorted((g.GetText(), g.GetPosition().x, g.GetPosition().y, g.GetTextAngle().AsDegrees(), g.IsMirrored())
                          for g in board.GetDrawings() if isinstance(g, self.p.PCB_TEXT))
        layout = read_layout(board, self.directory, 37, 41)
        self.assertEqual(len(layout['items']), len(expected))
        rev = revision(self.path, self.directory / 'silkscreen.json')
        save_layout(self.path, layout, rev, 37, 41)
        after = self.p.LoadBoard(str(self.path))
        self.assertEqual(before, self.fingerprint(after))
        actual = sorted((g.GetText(), g.GetPosition().x, g.GetPosition().y, g.GetTextAngle().AsDegrees(), g.IsMirrored())
                        for g in after.GetDrawings() if isinstance(g, self.p.PCB_TEXT))
        self.assertEqual(expected, actual)
        self.assertTrue(self.path.with_suffix('.silk-backup.kicad_pcb').exists())
        apply_saved(after, self.directory, 37, 41)
        self.assertEqual(len([g for g in after.GetDrawings() if isinstance(g, self.p.PCB_TEXT)]), len(expected))
        with self.assertRaisesRegex(ValueError, '변경'):
            save_layout(self.path, layout, rev, 37, 41)

    def test_rotated_svg_bottom_mirror_preserves_copper(self):
        for side in ['F.SilkS', 'B.SilkS']:
            board = self.p.LoadBoard(str(self.path))
            before = self.fingerprint(board)
            apply_layout(board, example(side), 37, 41)
            shapes = [g for g in board.GetDrawings() if g.GetLayer() in (self.p.F_SilkS, self.p.B_SilkS)]
            self.assertEqual(len(shapes), 2)
            bounds = sorted((round(self.p.ToMM(s.GetBoundingBox().GetCenter().y), 3),
                             round(self.p.ToMM(s.GetBoundingBox().GetCenter().x), 3)) for s in shapes)
            self.assertEqual([y for y, x in bounds], [10.5, 13.5])
            self.assertTrue(all(abs(x - (8 if side == 'F.SilkS' else 29)) < .001 for y, x in bounds))
            self.assertEqual(before, self.fingerprint(board))

    def test_external_edit_lock_and_invalid_save_do_not_touch_files(self):
        original = self.path.read_bytes()
        rev = revision(self.path, self.directory / 'silkscreen.json')
        lock = self.directory / f'~{BOARD.stem}.kicad_pro.lck'
        lock.touch()
        with self.assertRaisesRegex(ValueError, 'KiCad'):
            save_layout(self.path, example(), rev, 37, 41)
        lock.unlink()
        bad = example(); bad['items'][0]['side'] = 'F.Cu'
        with self.assertRaises(ValueError):
            save_layout(self.path, bad, rev, 37, 41)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.directory / 'silkscreen.json').exists())

    @unittest.skipUnless((KICAD / 'MacOS/kicad-cli').exists(), 'KiCad CLI required')
    def test_draft_check_finds_edge_interference_without_saving(self):
        original = self.path.read_bytes()
        layout = example()
        layout['items'][0].update(kind='text', text='OUTSIDE EDGE', x=36.9, y=22, size=1, thickness=.15)
        result = check_layout(self.path, layout, 37, 41, 'B')
        self.assertTrue(any(i['label'] == '보드 가장자리 간섭' for i in result['issues']))
        self.assertTrue(result['issues'][0]['boxes'])
        self.assertIn('viewBox="0 0 37 41"', result['svg'])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.directory / 'silkscreen.json').exists())


if __name__ == '__main__':
    unittest.main()
