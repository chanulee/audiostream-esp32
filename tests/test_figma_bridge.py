"""Figma bridge helpers; the HTTP round trip needs KiCad and runs by hand."""
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from figma_bridge import board_svg, plain_svg, projects, reference_layers  # noqa: E402
from silkscreen_editor import current_board  # noqa: E402

NS = '{http://www.w3.org/2000/svg}'


class BoardSvgTest(unittest.TestCase):
    SOURCE = ('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" '
              'viewBox="0 0 297 210"><title>x</title><desc>y</desc><rect width="1" height="1"/></svg>')

    def test_view_box_is_the_board(self):
        root = ET.fromstring(board_svg(self.SOURCE, 37, 41, False))
        self.assertEqual(root.get('viewBox'), '0 0 37 41')
        self.assertEqual([child.tag for child in root], [NS + 'rect'])

    def test_back_is_mirrored_about_the_board(self):
        root = ET.fromstring(board_svg(self.SOURCE, 37, 41, True))
        group = list(root)
        self.assertEqual(len(group), 1)
        self.assertEqual(group[0].get('transform'), 'translate(37 0) scale(-1 1)')
        self.assertEqual(group[0][0].tag, NS + 'rect')

    def test_assets_lose_namespace_prefixes(self):
        # Figma: "Failed to convert SVG file" on <ns0:svg>.
        source = ('<ns0:svg xmlns:ns0="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><ns0:title>t</ns0:title>'
                  '<ns0:g><ns0:circle r="1"/></ns0:g></ns0:svg>')
        plain = plain_svg(source)
        self.assertNotIn('ns0', plain)
        self.assertTrue(plain.startswith('<svg xmlns="http://www.w3.org/2000/svg"'))
        self.assertNotIn('title', plain)


class ProjectTest(unittest.TestCase):
    def test_current_board_and_ruler_variants(self):
        board = current_board()[0]
        table, default, variants = projects(board)
        self.assertEqual(default, 'original')
        self.assertEqual(table['original'][0], board)
        self.assertEqual(variants, [])
        ruler = ROOT / 'lovelace-ruler/lovelace-ruler.kicad_pcb'
        if (ruler.parent / 'variants.json').exists():
            table, default, variants = projects(ruler)
            self.assertIn(default, table)
            self.assertEqual({v['id'] for v in variants}, set(table))

    def test_reference_layers_follow_the_side(self):
        for side in 'FB':
            names = [name for name, *_ in reference_layers(side)]
            self.assertEqual(names, [f'{side}.Cu', f'{side}.Mask', f'{side}.SilkS', 'Edge.Cuts'])


if __name__ == '__main__':
    unittest.main()
