"""Run with .venv/bin/python -m unittest test_render_svg -v."""
import math
import unittest
import xml.etree.ElementTree as ET
import render_svg as r
import svg_viewer as viewer
import silk_geometry as silk


class SvgTests(unittest.TestCase):
    def test_parser_quotes_and_balance(self):
        board = r.parse_board(r'(kicad_pcb (title "a (b) \"quoted\""))')
        self.assertEqual(r.field(board, 'title'), ['a (b) "quoted"'])
        for bad in ('(kicad_pcb', '(kicad_pcb))', '(wrong)', '(kicad_pcb)(kicad_pcb)'):
            with self.assertRaises(ValueError):
                r.parse_board(bad)

    def test_footprint_rotation(self):
        fp = ['footprint', ['at', '10', '20', '90']]
        x, y = r.position(fp, 2, 3)
        self.assertAlmostEqual(x, 13)
        self.assertAlmostEqual(y, -18)

    def test_cube_hidden_edges_and_vector_output(self):
        r.load_occ()
        cube = r.Box(10, 10, 10).Shape()
        paths = r.project(cube, -65, 38)
        # An opaque cube exposes nine edges in isometric projection, not twelve.
        self.assertEqual(len(paths), 9)
        self.assertTrue(all(math.isfinite(v) for p in paths for xy in p for v in xy))
        root = ET.fromstring(r.svg(paths, 'A&B', .04, 'transparent'))
        self.assertEqual(root.find(f'{{{r.NS}}}title').text, 'A&B')
        self.assertEqual(len(root.findall(f'.//{{{r.NS}}}path')), 9)
        self.assertIsNone(root.find(f'{{{r.NS}}}rect'))
        self.assertIsNone(root.find(f'.//{{{r.NS}}}image'))

    def test_current_board_geometry(self):
        r.load_occ()
        board = r.parse_board(r.resolve_board().read_text())
        body, thickness = r.board_body(board)
        from OCP.BRepCheck import BRepCheck_Analyzer
        self.assertTrue(BRepCheck_Analyzer(body).IsValid())
        self.assertEqual(thickness, 1.6)
        root = ET.fromstring(r.assembly_top(board, .045, '#ffffff'))
        refs = [n.text for n in root.findall(f'.//{{{r.NS}}}text')]
        self.assertIn('U6', refs)
        self.assertIn('J1', refs)
        self.assertNotIn('VBUS', refs)  # Bottom-side test pads stay on the bottom.

    def test_xray_faces_match_viewer_alpha(self):
        r.load_occ()
        mesh = viewer.mesh_data(r.Box(10, 10, 10).Shape())
        faces = r.xray_faces(mesh['triangles'], mesh['normals'], -65, 38, opacity=.1)
        regions = [region for _, group in faces for region in group]
        loops = [loop for region in regions for loop in region]
        # Six flat faces: one region and one outline each (front three, back three).
        self.assertEqual(len(regions), 6)
        self.assertEqual(len(loops), 6)
        self.assertTrue(all(len(loop) == 4 for loop in loops))
        self.assertTrue(all(.02 <= a <= .1 for a, _ in faces))
        paths = r.project(r.Box(10, 10, 10).Shape(), -65, 38, detail=True, hidden=True)
        root = ET.fromstring(r.svg(paths, 'x', .04, '#101114'))
        r.append_xray_faces(root, faces)
        root = ET.fromstring(ET.tostring(root))
        layers = [n.get('id') for n in root if n.tag == f'{{{r.NS}}}g']
        self.assertEqual(len(root.findall(f'.//{{{r.NS}}}g[@id="xray-faces"]//{{{r.NS}}}path')), 6)
        self.assertEqual(layers, ['xray-faces', 'visible-edges'])
        self.assertEqual(root.find(f'{{{r.NS}}}g[@id="visible-edges"]').get('stroke-opacity'), '0.38')
        # Face outlines land on the projected cube edges.
        xs = [x for p in paths for x, _ in p]
        fx = [x for loop in loops for x, _ in loop]
        self.assertAlmostEqual(min(xs), min(fx), places=3)
        self.assertAlmostEqual(max(xs), max(fx), places=3)

    def test_interactive_mesh_has_faces_and_edges(self):
        r.load_occ()
        mesh = viewer.mesh_data(r.Box(10, 10, 10).Shape())
        self.assertEqual(len(mesh['triangles']), 12 * 9)
        self.assertEqual(len(mesh['lines']), 12 * 6)
        self.assertTrue(all(math.isfinite(v) for values in mesh.values() for v in values))
        self.assertEqual(len(mesh['normals']),len(mesh['triangles']))
        self.assertEqual(len(mesh['colors']),len(mesh['triangles']))
        self.assertEqual(len(mesh['clean_lines']),len(mesh['lines']))

    def test_step_original_face_colors(self):
        import step_colors
        r.load_occ()
        shape,colors,stats=step_colors.read_colored_step(r.ROOT/'lib/3d/TYPE-C-31-M-12_C165948.step')
        self.assertEqual(stats['faces'],stats['colored_faces'])
        self.assertGreaterEqual(len(set(map(tuple,colors))),4)
        # USB STEP includes gold contacts, silver housing and dark plastic.
        self.assertTrue(any(c[0]>.8 and c[1]>.3 and c[2]<.05 for c in colors))
        self.assertTrue(any(max(c)<.06 for c in colors))
        self.assertTrue(any(min(c)>.65 for c in colors))
        _,jack_colors,jack_stats=step_colors.read_colored_step(r.ROOT/'lib/3d/PJ-320D_C431535.step')
        self.assertEqual(jack_stats['faces'],jack_stats['colored_faces'])
        self.assertTrue(any(max(c)<.05 for c in jack_colors))

    def test_all_edge_svg_includes_hidden_cube_edges(self):
        r.load_occ()
        cube=r.Box(10,10,10).Shape()
        self.assertEqual(len(r.project(cube,-65,38,detail=True,hidden=True)),12)

    def test_interactive_request_validation(self):
        valid = dict(azimuth=-65, elevation=-90, stroke=.045, background='transparent', ink='#123456')
        self.assertEqual(viewer.validate_view(valid), (-65, -90, .045, 'transparent', '#123456'))
        for key, value in [('azimuth', float('nan')), ('elevation', 91), ('stroke', 0),
                           ('ink', '<script>'), ('background', 'url(file:///tmp/x)'), ('azimuth', True)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                viewer.validate_view({**valid, key: value})
        with self.assertRaises(ValueError):
            viewer.validate_view([])

    def test_usb_mounting_features_match_the_pcb(self):
        r.load_occ()
        board = r.parse_board(r.resolve_board().read_text())
        fp = next(f for f in r.children(board,'footprint') if r.reference(f)=='J1')
        model = r.children(fp,'model')[0]
        # These are measured STEP feature coordinates, independent of its placement offsets.
        # Raw locating pegs: (+/-2.89,-3.65); contact plane: z=0; connector mouth: y=2.60.
        for x in (-2.89,2.89):
            marker = r.Box(r.gp.gp_Pnt(x-0.001,-3.651,-.001),.002,.002,.002).Shape()
            placed = r.placed_model(marker,model,fp,1.6)
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib
            box = Bnd_Box(); BRepBndLib.AddOptimal_s(placed,box)
            lo_x,lo_y,lo_z,hi_x,hi_y,hi_z = box.Get()
            peg = next(p for p in r.children(fp,'pad') if not p[1] and abs(float(r.field(p,'at')[0])+x)<.001)
            expected = r.position(fp,*r.numbers(peg,'at')[:2])
            self.assertAlmostEqual((lo_x+hi_x)/2,expected[0],places=4)
            self.assertAlmostEqual((lo_y+hi_y)/2,expected[1],places=4)
            self.assertAlmostEqual((lo_z+hi_z)/2,1.6,places=4)
        self.assertEqual(r.numbers(r.field(model,'offset'),'xyz'),[0,-1.05,0])
        reader=r.Reader();reader.ReadFile(str(r.ROOT/'lib/3d/TYPE-C-31-M-12_C165948.step'));reader.TransferRoots()
        box=Bnd_Box();BRepBndLib.AddOptimal_s(r.placed_model(reader.OneShape(),model,fp,1.6),box)
        self.assertAlmostEqual(-box.Get()[1],41,places=3)  # Mouth flush with bottom Edge.Cuts.
        self.assertAlmostEqual(box.Get()[5],4.851,places=3)

    def test_back_silk_matches_native_kicad_coordinates(self):
        board=r.parse_board(r.resolve_board().read_text())
        text=next(n for n in r.children(board,'gr_text') if n[1].startswith('4.75'))
        points,fill,width=silk.text_paths(text)[0]
        # Checked against KiCad's native layer-B_Silkscreen.svg, not a browser font.
        self.assertAlmostEqual(points[0][0],17.2138,places=4)
        self.assertAlmostEqual(points[0][1],21.6946,places=4)
        self.assertEqual(width,.12)
        contours=silk.back_contours(board)
        self.assertEqual(sum(fill for _,fill,_ in contours),184)
        root=ET.fromstring(silk.bottom_svg(board,.045,'#ffffff',contours))
        self.assertIsNotNone(root.find(f'{{{r.NS}}}g[@id="back-silkscreen"]'))
        top=ET.fromstring(r.svg([[(0,0),(37,41)]],'test',.045,'transparent'))
        silk.append_svg(top,contours,-65,38)
        self.assertIsNone(top.find(f'{{{r.NS}}}g[@id="back-silkscreen"]'))

    def test_footprint_silk_keep_upright(self):
        from copy import deepcopy
        board=r.parse_board(r.resolve_board().read_text())
        fp=next(f for f in r.children(board,'footprint') if r.reference(f)=='VBUS')
        ref=r.children(fp,'property')[0]
        self.assertEqual(r.field(ref,'at')[-1],'180')
        straight=deepcopy(ref)
        r.children(straight,'at')[0][-1]='0'
        self.assertEqual(silk.text_paths(ref,fp),silk.text_paths(straight,fp))
        points,_,_=silk.text_paths(ref,fp)[0]
        self.assertAlmostEqual(points[0][0],4.3667,places=4)
        self.assertAlmostEqual(points[0][1],32.4623,places=4)
        unlocked=deepcopy(ref);unlocked.append(['unlocked','yes'])
        self.assertNotEqual(silk.text_paths(unlocked,fp),silk.text_paths(straight,fp))

    def test_perspective_projection_and_lens_validation(self):
        r.load_occ()
        view=r.projector(-90,90,(0,0,0),100)
        x,y,_=view.Project(r.gp.gp_Pnt(10,0,20))
        self.assertAlmostEqual(x,12.5)
        self.assertAlmostEqual(y,0)
        self.assertEqual(len(r.project(r.Box(10,10,10).Shape(),-65,38,(5,5,5),100)),9)
        self.assertEqual(viewer.validate_camera({'projection':'perspective','lens':35}),('perspective',35,1))
        for lens in [0,121,float('nan'),True,'50']:
            with self.assertRaises(ValueError):viewer.validate_camera({'lens':lens})
        with self.assertRaises(ValueError):viewer.validate_camera({'aspect':0})
        root=ET.fromstring(r.svg([[(0,0),(1,1)]],'camera',.045,'transparent'))
        contour=[([(0,0),(1,0),(1,1),(0,0)],True,0)]
        silk.append_svg(root,contour,90,-1,camera_center=(0,0,5),focus=100)
        self.assertIsNone(root.find(f'{{{r.NS}}}g[@id="back-silkscreen"]'))
        silk.append_svg(root,contour,90,-45,camera_center=(0,0,5),focus=100)
        self.assertIsNotNone(root.find(f'{{{r.NS}}}g[@id="back-silkscreen"]'))


if __name__ == '__main__':
    unittest.main()
