"""Portable board discovery; no STEP dependencies or AS-006 fixtures needed."""
import json
from pathlib import Path
import tempfile
import unittest

import render_svg as render


class BoardInputTests(unittest.TestCase):
    def test_version_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ('007', '008'):
                root = Path(tmp) / f'lovelace-as-{version}'
                root.mkdir()
                name = root.name
                board = root / f'{name}.kicad_pcb'
                board.write_text('(kicad_pcb)')
                (root / 'backup.kicad_pcb').write_text('(kicad_pcb)')
                (root / 'placement.json').write_text(json.dumps({'board': {'name': name}}))
                self.assertEqual(render.resolve_board(root=root), board.resolve())
                self.assertEqual(render.resolve_board(board), board.resolve())

    def test_no_manifest_requires_one_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                render.resolve_board(root=root)
            board = root / 'custom.kicad_pcb'
            board.touch()
            self.assertEqual(render.resolve_board(root=root), board.resolve())
            (root / 'another.kicad_pcb').touch()
            with self.assertRaises(ValueError):
                render.resolve_board(root=root)

    def test_stale_manifest_does_not_select_another_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'old.kicad_pcb').touch()
            manifest = root / 'placement.json'
            manifest.write_text(json.dumps({'board': {'name': 'missing'}}))
            with self.assertRaisesRegex(ValueError, 'does not exist'):
                render.resolve_board(root=root)
            manifest.write_text(json.dumps({'board': {'name': '../outside'}}))
            with self.assertRaisesRegex(ValueError, 'filename stem'):
                render.resolve_board(root=root)


if __name__ == '__main__':
    unittest.main()
