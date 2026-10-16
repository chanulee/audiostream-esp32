#!/usr/bin/env python3
"""Interactive local 3D viewer with exact STEP → SVG export.

Run: .venv/bin/python svg_viewer.py
"""
import argparse
import html
import json
import math
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import render_svg as render
import silk_geometry as silk


def mesh_data(shape, face_colors=None):
    """Tessellate faces for depth and sample real STEP edges for the live view."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_REVERSED
    from OCP.BRepLib import BRepLib_ToolTriangulatedShape
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.GeomAbs import GeomAbs_C0
    from OCP.TopExp import TopExp
    mesher = BRepMesh_IncrementalMesh(shape, 0.035, False, 0.3, True)
    if not mesher.IsDone():
        raise ValueError('Preview meshing failed')
    triangles, lines, clean_lines, normals, colors = [], [], [], [], []
    face_index = 0
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        location = TopLoc_Location()
        face = TopoDS.Face_s(faces.Current())
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is not None:
            BRepLib_ToolTriangulatedShape.ComputeNormals_s(face,mesh)
            transform = location.Transformation()
            color = face_colors[face_index] if face_colors else [.2,.2,.2]
            sign = -1 if face.Orientation() == TopAbs_REVERSED else 1
            for i in range(1, mesh.NbTriangles() + 1):
                for index in mesh.Triangle(i).Get():
                    p = mesh.Node(index).Transformed(transform)
                    triangles.extend(round(v, 5) for v in (p.X(), p.Y(), p.Z()))
                    normal = mesh.Normal(index).Transformed(transform)
                    normals.extend(round(sign*v,6) for v in (normal.X(),normal.Y(),normal.Z()))
                    colors.extend(color)
        face_index += 1
        faces.Next()
    edges = TopExp_Explorer(shape, TopAbs_EDGE)
    ancestors=TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape,TopAbs_EDGE,TopAbs_FACE,ancestors)
    seen = set()
    while edges.More():
        edge=TopoDS.Edge_s(edges.Current())
        adjacent=ancestors.FindFromKey(edge)
        sharp=adjacent.Size()!=2 or (not adjacent.First().IsSame(adjacent.Last()) and
                BRep_Tool.Continuity_s(edge,TopoDS.Face_s(adjacent.First()),TopoDS.Face_s(adjacent.Last()))==GeomAbs_C0)
        curve = BRepAdaptor_Curve(edge)
        sample = GCPnts_QuasiUniformDeflection(curve, 0.025)
        if not sample.IsDone():
            raise ValueError('Preview edge sampling failed')
        points = [tuple(round(v, 5) for v in (p.X(), p.Y(), p.Z()))
                  for p in (sample.Value(i) for i in range(1, sample.NbPoints() + 1))]
        for a, b in zip(points, points[1:]):
            key = tuple(sorted((a, b)))
            if a != b and key not in seen:
                seen.add(key)
                lines.extend((*a, *b))
                if sharp:clean_lines.extend((*a,*b))
        edges.Next()
    if not triangles or not lines:
        raise ValueError('Empty preview mesh')
    return dict(triangles=triangles, lines=lines,clean_lines=clean_lines,normals=normals,colors=colors)


def validate_view(data):
    if not isinstance(data, dict):
        raise ValueError('Expected an object')
    az, el, stroke = (data.get(k) for k in ('azimuth', 'elevation', 'stroke'))
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (az, el, stroke)):
        raise ValueError('Angles and line width must be finite numbers')
    if not -90 <= el <= 90 or not 0.015 <= stroke <= 1 or abs(az) > 36000:
        raise ValueError('View is outside the supported range')
    background = data.get('background')
    ink = data.get('ink')
    if background != 'transparent' and not (isinstance(background, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', background)):
        raise ValueError('Invalid background')
    if not isinstance(ink, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', ink):
        raise ValueError('Invalid line color')
    return az, el, stroke, background, ink


def validate_camera(data):
    projection = data.get('projection','orthographic')
    lens = data.get('lens',50)
    aspect = data.get('aspect',1)
    if projection not in ('orthographic','perspective') or type(lens) not in (int,float) or not math.isfinite(lens) or not 18 <= lens <= 120:
        raise ValueError('Invalid camera: choose orthographic/perspective and 18–120 mm lens')
    if type(aspect) not in (int,float) or not math.isfinite(aspect) or not .05<=aspect<=20:
        raise ValueError('Invalid viewport aspect ratio')
    return projection,lens,aspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', nargs='?', help='PCB path; default: parent placement.json or sole PCB')
    parser.add_argument('--port', type=int, default=8877)
    parser.add_argument('--fetch-models', action='store_true')
    args = parser.parse_args()
    try:
        board_path = render.resolve_board(args.board)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    board_name = board_path.stem
    board = render.parse_board(board_path.read_text())
    render.load_occ()
    shape, count = render.assembly(board, board_path, render.TOOL_DIR / '.models' / render.MODEL_REV, args.fetch_models)
    print('Preparing interactive mesh…', flush=True)
    contours = silk.back_contours(board)
    from step_colors import scene_mesh
    import gzip,hashlib,inspect
    digest=hashlib.sha256(board_path.read_bytes()+inspect.getsource(mesh_data).encode())
    sources=[render.TOOL_DIR/n for n in ('step_colors.py','silk_geometry.py','newstroke_ascii.json','render_svg.py')]
    sources += sorted({render.model_path(m,board_path,render.TOOL_DIR/'.models'/render.MODEL_REV,False)
                       for fp in render.children(board,'footprint') for m in render.children(fp,'model')})
    for path in sources:digest.update(path.read_bytes())
    cache=render.TOOL_DIR/'.cache';cache.mkdir(exist_ok=True)
    metadata_path=cache/'scene.json';data_path=cache/'scene.json.gz'
    try:metadata=json.loads(metadata_path.read_text())
    except (OSError,ValueError):metadata={}
    if metadata.get('key')==digest.hexdigest() and data_path.is_file():
        geometry=data_path.read_bytes();center=metadata['center'];radius=metadata['radius']
        print('Using cached colored mesh',flush=True)
    else:
        mesh = scene_mesh(board,board_path,mesh_data)
        center = [(min(mesh['triangles'][axis::3])+max(mesh['triangles'][axis::3]))/2 for axis in range(3)]
        radius = max(math.dist(center,mesh['triangles'][i:i+3]) for i in range(0,len(mesh['triangles']),3))
        mesh.update(center=center,radius=radius)
        mesh['silk'] = silk.triangles(contours)
        geometry=gzip.compress(json.dumps(mesh,separators=(',',':')).encode(),compresslevel=5)
        metadata=dict(key=digest.hexdigest(),center=center,radius=radius,color_sources=mesh['color_sources'])
        temp=cache/'scene.tmp';temp.write_bytes(geometry);temp.replace(data_path)
        metadata_path.write_text(json.dumps(metadata,indent=2))
        del mesh
    output_dir = board_path.parent / 'renders/svg'
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir/'color-sources.json').write_text(json.dumps(metadata['color_sources'],indent=2))
    token = secrets.token_urlsafe(24)
    config = json.dumps(dict(token=token, models=count, boardName=board_name)).replace('<', '\\u003c')
    page = (render.TOOL_DIR / 'svg_viewer.html').read_text().replace('__CONFIG__', config)
    page = page.replace('__BOARD_NAME__', html.escape(board_name)).replace('__MODEL_COUNT__', str(count))
    bottom = render.ET.fromstring(silk.bottom_svg(board,.045,'#ffffff',contours))
    bottom.set('style','display:none')
    page = page.replace('__TOP_SVG__', render.assembly_top(board, .045, '#ffffff'))
    page = page.replace('__BOTTOM_SVG__', render.ET.tostring(bottom,encoding='unicode')).encode()
    assets = {'/': (page, 'text/html; charset=utf-8'),
              '/mesh.json': (geometry, 'application/json'),
              '/viewer.js': ((render.TOOL_DIR / 'svg_viewer.js').read_bytes(), 'text/javascript; charset=utf-8'),
              '/engine.js': ((render.TOOL_DIR / 'render_engine.js').read_bytes(),'text/javascript; charset=utf-8')}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if urlsplit(self.path).path == '/mesh.json':self.send_header('Content-Encoding','gzip')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send(403, b'Local access only')
                return
            path = urlsplit(self.path).path
            if path in assets:
                data, kind = assets[path]
                self.send(200, data, kind)
            else:
                self.send(404, b'Not found')

        def do_POST(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send(403, b'Local access only')
                return
            if self.path != '/api/project':
                self.send(404, b'Not found')
                return
            if self.headers.get('X-PCB-Viewer') != token:
                self.send(403, b'Invalid viewer session')
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                az, el, stroke, background, ink = validate_view(data)
                style=data.get('style','line')
                if style not in ('line','detail','wire','xray','studio','original','material','normal'):
                    raise ValueError('Invalid render style')
                projection,lens,aspect = validate_camera(data)
                perspective = projection == 'perspective'
                camera_center = center if perspective else (0,0,0)
                focus = radius*1.12*max(1,1/aspect)*lens/12 if perspective else None
                with lock:
                    paths = render.project(shape, az, el,camera_center,focus,
                                           detail=style in ('detail','wire','xray'),hidden=style in ('wire','xray'))
                root = render.ET.fromstring(render.svg(paths, f'{board_name} / {az:g}°, {el:g}°', stroke, background))
                root.find(f'{{{render.NS}}}g').set('stroke', ink)
                root.find(f'{{{render.NS}}}desc').text += f' Edge style: {style}. Material and lighting are exported as PNG, not vector fills.'
                root.find(f'{{{render.NS}}}desc').text += f' Projection: {projection}; lens: {lens:g} mm (36x24 mm sensor); camera distance: {focus if focus is not None else "infinite"} mm.'
                silk.append_svg(root, contours, az, el, ink,camera_center,focus)
                self.send(200, render.ET.tostring(root, encoding='utf-8'), 'image/svg+xml')
            except (ValueError, TypeError) as exc:
                self.send(400, str(exc).encode())
            except Exception as exc:
                print('SVG projection failed:', exc, flush=True)
                self.send(500, 'SVG 생성에 실패했습니다. 서버 로그를 확인하세요.'.encode())

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Board: {board_path}\nInteractive 3D viewer: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
