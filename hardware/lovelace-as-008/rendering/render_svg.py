#!/usr/bin/env python3
"""Actual STEP geometry → hidden-line-removed SVG; no bitmap tracing or KiCad runtime.

First run (in rendering/): python3 -m venv .venv
           .venv/bin/pip install -r requirements-svg.txt
           .venv/bin/python render_svg.py --fetch-models
"""
import argparse
import html
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent
MODEL_REV = '10.0.0'
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)


def resolve_board(board=None, root=None):
    """Resolve relative to this tool's parent, independently of the shell cwd."""
    if board is not None:
        path = Path(board).resolve()
    else:
        root = Path(root) if root is not None else ROOT
        placement = root / 'placement.json'
        if placement.is_file():
            name = json.loads(placement.read_text())['board']['name']
            if not isinstance(name, str) or not name or Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('placement.json board.name must be a filename stem')
            path = root / f'{name}.kicad_pcb'
        else:
            candidates = sorted(root.glob('*.kicad_pcb'))
            if len(candidates) != 1:
                raise ValueError(f'Expected one PCB in {root}; specify a board path or placement.json board.name')
            path = candidates[0]
    if not path.is_file():
        raise ValueError(f'PCB file does not exist: {path}')
    return path.resolve()


def children(node, key):
    return [n for n in node if isinstance(n, list) and n and n[0] == key]


def field(node, key, default=()):
    found = children(node, key)
    return found[0][1:] if found else default


def numbers(node, key, default=()):
    return list(map(float, field(node, key, default)))


def parse_board(text):
    """KiCad's balanced S-expressions; quoted parentheses remain literal text."""
    stack, roots = [], []
    for match in re.finditer(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)', text):
        token = match[1]
        if token == '(':
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
        elif token == ')':
            if not stack:
                raise ValueError('Unexpected closing parenthesis')
            stack.pop()
        else:
            if not stack:
                raise ValueError('Expected an S-expression')
            if token.startswith('"'):
                token = re.sub(r'\\(.)', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), token[1:-1])
            stack[-1].append(token)
    if stack or len(roots) != 1 or roots[0][0] != 'kicad_pcb':
        raise ValueError('Invalid KiCad PCB')
    return roots[0]


def position(fp, x, y):
    """KiCad screen coordinates → right-handed world (Y up), in mm."""
    fx, fy, *angle = numbers(fp, 'at')
    a = math.radians(angle[0] if angle else 0)
    return fx + x * math.cos(a) + y * math.sin(a), -fy + x * math.sin(a) - y * math.cos(a)


def reference(fp):
    return next((n[2] for n in children(fp, 'property') if n[1] == 'Reference'), fp[1])


def model_path(model, board_path, cache, fetch):
    name = model[1]
    name = name.replace('${KIPRJMOD}', str(board_path.parent))
    variable = re.match(r'^\$\{(KICAD\d*_3DMODEL_DIR)\}/(.+)$', name)
    if not variable:
        path = Path(os.path.expandvars(name))
        return path if path.is_absolute() else board_path.parent / path
    env, relative = variable.groups()
    candidates = [Path(os.environ[env]) / relative] if env in os.environ else []
    candidates += [Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels') / relative,
                   Path('/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/3dmodels') / relative,
                   cache / relative]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # The board's older TI-specific filename names the same DSG WSON-8 package.
    relative = relative.replace('Texas_DSG0008A_WSON-8-', 'WSON-8-')
    target = cache / relative
    if target.is_file():
        return target
    if fetch:
        if '..' in Path(relative).parts or Path(relative).is_absolute():
            raise ValueError('Unsafe library model path')
        url = f'https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/{MODEL_REV}/{relative}'
        print('Downloading', relative, flush=True)
        context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform == 'darwin' else None)
        with urllib.request.urlopen(url, timeout=60, context=context) as response:
            data = response.read()
        if not data.lstrip().startswith(b'ISO-10303-21;'):
            raise ValueError(f'Not a STEP model: {url}')
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.tmp')
        temp.write_bytes(data)
        temp.replace(target)
    return target


def load_occ():
    # Keep --help and parser checks usable without the geometry dependency.
    global gp, Builder, Transform, Box, Cylinder, Cut, Fuse, Reader, Done
    from OCP import gp
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform as Transform
    from OCP.BRep import BRep_Builder as Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox as Box, BRepPrimAPI_MakeCylinder as Cylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut as Cut
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse as Fuse
    from OCP.STEPControl import STEPControl_Reader as Reader
    from OCP.IFSelect import IFSelect_RetDone as Done


def moved(shape, xyz=(0, 0, 0), angles=(0, 0, 0)):
    for direction, angle in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), angles):
        if angle:
            tr = gp.gp_Trsf()
            tr.SetRotation(gp.gp_Ax1(gp.gp_Pnt(), gp.gp_Dir(*direction)), math.radians(angle))
            shape = Transform(shape, tr, False).Shape()
    tr = gp.gp_Trsf()
    tr.SetTranslation(gp.gp_Vec(*xyz))
    return Transform(shape, tr, False).Shape()


def board_body(board):
    """The AS-006 outline is a rectangle. Refuse other outlines rather than invent one."""
    edges = [n for n in board if isinstance(n, list) and field(n, 'layer') == ['Edge.Cuts']]
    if len(edges) != 4 or any(n[0] != 'gr_line' for n in edges):
        raise ValueError('This renderer currently requires four rectangular Edge.Cuts lines')
    points = [tuple(numbers(e, k)) for e in edges for k in ('start', 'end')]
    xs, ys = sorted(set(p[0] for p in points)), sorted(set(p[1] for p in points))
    if len(xs) != 2 or len(ys) != 2 or any(points.count(p) != 2 for p in set(points)):
        raise ValueError('Edge.Cuts must form a closed rectangle')
    if any(numbers(e, 'start')[0] != numbers(e, 'end')[0] and
           numbers(e, 'start')[1] != numbers(e, 'end')[1] for e in edges):
        raise ValueError('Diagonal Edge.Cuts are unsupported')
    thickness = numbers(field(board, 'general'), 'thickness')[0]
    body = Box(gp.gp_Pnt(xs[0], -ys[1], 0), xs[1] - xs[0], ys[1] - ys[0], thickness).Shape()
    # Through holes include connector locating pins and the mounting hole.
    for fp in children(board, 'footprint'):
        for pad in children(fp, 'pad'):
            drill = field(pad, 'drill')
            if not drill:
                continue
            if children(drill, 'offset'):
                raise ValueError('Offset drills are unsupported')
            x, y, *angle = numbers(pad, 'at', (0, 0))
            x, y = position(fp, x, y)
            if drill[0] == 'oval':
                w, h = map(float, drill[1:3])
                radius, span = min(w, h) / 2, abs(w - h)
                if span <= 0:
                    tool = Cylinder(radius, thickness + 2).Shape()
                else:
                    tool = Box(gp.gp_Pnt(-span / 2, -radius, 0), span, radius * 2, thickness + 2).Shape()
                    for dx in (-span / 2, span / 2):
                        end = Cylinder(gp.gp_Ax2(gp.gp_Pnt(dx, 0, 0), gp.gp_Dir(0, 0, 1)), radius, thickness + 2).Shape()
                        tool = Fuse(tool, end).Shape()
                tool = moved(tool, (x, y, -1), (0, 0, (angle[0] if angle else 0) + (90 if h > w else 0)))
            else:
                tool = Cylinder(gp.gp_Ax2(gp.gp_Pnt(x, y, -1), gp.gp_Dir(0, 0, 1)), float(drill[0]) / 2, thickness + 2).Shape()
            cut = Cut(body, tool)
            if not cut.IsDone():
                raise ValueError('Could not cut a board hole')
            body = cut.Shape()
    return body, thickness


def assembly(board, board_path, cache, fetch):
    from OCP.TopoDS import TopoDS_Compound
    shape = TopoDS_Compound()
    builder = Builder()
    builder.MakeCompound(shape)
    body, thickness = board_body(board)
    builder.Add(shape, body)
    loaded, count = {}, 0
    missing = []
    for fp in children(board, 'footprint'):
        if children(fp, 'model') and field(fp, 'layer') != ['F.Cu']:
            # shortcut: AS-006 is single-sided; reject bottom parts until their transforms are supported.
            raise ValueError(f'Bottom footprint unsupported: {reference(fp)}')
        for model in children(fp, 'model'):
            if 'hide' in model:
                continue
            path = model_path(model, board_path, cache, fetch)
            if not path.is_file():
                missing.append(f'{reference(fp)}: {path}')
                continue
            if path not in loaded:
                reader = Reader()
                if reader.ReadFile(str(path)) != Done or reader.TransferRoots() == 0:
                    raise ValueError(f'Cannot read STEP: {path}')
                loaded[path] = reader.OneShape()
            part = placed_model(loaded[path],model,fp,thickness)
            builder.Add(shape, part)
            count += 1
    if missing:
        raise ValueError('Missing models; run with --fetch-models or set KICAD10_3DMODEL_DIR:\n' + '\n'.join(missing))
    print(f'Assembled {count} placed STEP models ({len(loaded)} unique files)', flush=True)
    return shape, count


def placed_model(part, model, fp, thickness):
    scale = numbers(field(model, 'scale'), 'xyz', (1, 1, 1))
    if scale != [1., 1., 1.]:
        raise ValueError(f'Non-unit model scale unsupported: {reference(fp)}')
    angles = numbers(field(model, 'rotate'), 'xyz', (0, 0, 0))
    offset = numbers(field(model, 'offset'), 'xyz', (0, 0, 0))
    # KiCad model rotations use clockwise angles; footprint rotation is CCW in Y-up.
    part = moved(part, offset, [-a for a in angles])
    x, y, *angle = numbers(fp, 'at')
    return moved(part, (x, -y, thickness), (0, 0, angle[0] if angle else 0))


def projector(azimuth, elevation, center=(0,0,0), focus=None):
    from OCP.HLRAlgo import HLRAlgo_Projector
    az, el = map(math.radians, (azimuth, elevation))
    direction = gp.gp_Dir(math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    right = gp.gp_Dir(-math.sin(az), math.cos(az), 0)
    axes = gp.gp_Ax2(gp.gp_Pnt(*center),direction,right)
    return HLRAlgo_Projector(axes,focus) if focus is not None else HLRAlgo_Projector(axes)


def project(shape, azimuth, elevation, camera_center=(0,0,0), focus=None, detail=False, hidden=False):
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(projector(azimuth,elevation,camera_center,focus))
    algo.Update()
    algo.Hide()
    result = HLRBRep_HLRToShape(algo)
    paths = []
    # Exclude smooth seam/isoparametric edges; retain sharp edges and silhouettes.
    compounds=[result.VCompound(),result.Rg1LineVCompound(),result.OutLineVCompound()]
    if detail:compounds.append(result.RgNLineVCompound())
    if hidden:
        compounds.extend([result.HCompound(),result.Rg1LineHCompound(),result.RgNLineHCompound(),result.OutLineHCompound()])
    for visible in compounds:
        if visible.IsNull():
            continue
        edges = TopExp_Explorer(visible, TopAbs_EDGE)
        while edges.More():
            curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges.Current()))
            sample = GCPnts_QuasiUniformDeflection(curve, 0.008)
            if not sample.IsDone():
                raise ValueError('Curve sampling failed')
            pts = [(sample.Value(i).X(), -sample.Value(i).Y()) for i in range(1, sample.NbPoints() + 1)]
            if len(pts) > 1:
                paths.append(pts)
            edges.Next()
    if not paths:
        raise ValueError('Projection contains no visible edges')
    return paths


XRAY_FACE = '#a6b8d1'  # render_engine.js mode 6: vec3(.65,.72,.82)
XRAY_EDGE_ALPHA = .38  # render_engine.js edge alpha in X-ray


def xray_faces(triangles, normals, azimuth, elevation, camera_center=(0,0,0), focus=None,
               opacity=.08, levels=24):
    """Translucent faces of the live X-ray view as vector regions.

    The viewer draws every triangle, front and back, additively with alpha
    opacity * (0.2 + 0.8 * (1 - |n.v|)^2). Triangles are quantised to
    `levels` alpha steps; connected same-step triangles that face the same
    way merge into one region (outline plus holes), so a flat face is one
    path. Regions stay separate so overlapping parts stack as on screen.
    Returns [(alpha, [region, ...]), ...]; a region is a list of loops in the
    coordinates of project()."""
    from OCP.gp import gp_Pnt, gp_Pnt2d
    proj = projector(azimuth, elevation, camera_center, focus)
    az, el = map(math.radians, (azimuth, elevation))
    eye = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    camera = tuple(c + e * focus for c, e in zip(camera_center, eye)) if focus else None
    cache, out = {}, gp_Pnt2d()

    def to2d(key):
        if key not in cache:
            proj.Project(gp_Pnt(*key), out)
            cache[key] = (out.X(), -out.Y())
        return cache[key]

    groups = {}
    for t in range(0, len(triangles), 9):
        keys = [tuple(triangles[t + i:t + i + 3]) for i in (0, 3, 6)]
        n = [sum(normals[t + i + axis] for i in (0, 3, 6)) for axis in range(3)]
        length = math.hypot(*n)
        if length < 1e-12:
            continue
        n = [v / length for v in n]
        if camera:
            mid = [sum(k[axis] for k in keys) / 3 for axis in range(3)]
            v = [c - m for c, m in zip(camera, mid)]
            vl = math.hypot(*v)
            v = [c / vl for c in v]
        else:
            v = eye
        facing = sum(a * b for a, b in zip(n, v))
        alpha = .2 + .8 * (1 - abs(facing)) ** 2
        level = min(levels, max(1, round(alpha * levels)))
        a, b, c = (to2d(k) for k in keys)
        area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(area) < 1e-9:
            continue
        if area < 0:  # orient every triangle the same way on paper
            keys = [keys[0], keys[2], keys[1]]
        edges, parent = groups.setdefault((level, facing > 0), ({}, {}))
        for p, q in zip(keys, keys[1:] + keys[:1]):
            if (q, p) in edges:
                del edges[(q, p)]  # interior edge shared with a neighbour
            else:
                edges[(p, q)] = True
        roots = [find(parent, k) for k in keys]
        for r in roots[1:]:
            parent[r] = roots[0]
    result = {}
    for (level, _), (edges, parent) in sorted(groups.items()):
        nexts = {}
        for p, q in edges:
            nexts.setdefault(p, []).append(q)
        regions = {}
        while nexts:
            start = next(iter(nexts))
            loop, p = [start], start
            while True:
                q = nexts[p].pop()
                if not nexts[p]:
                    del nexts[p]
                if q == start or q not in nexts:
                    break
                loop.append(q)
                p = q
            if len(loop) > 2:
                regions.setdefault(find(parent, start), []).append([to2d(k) for k in loop])
        result.setdefault(level, []).extend(regions.values())
    return [(opacity * level / levels, regions) for level, regions in sorted(result.items()) if regions]


def find(parent, key):
    parent.setdefault(key, key)
    while parent[key] != key:
        parent[key] = parent[parent[key]]
        key = parent[key]
    return key


def append_xray_faces(root, faces):
    """Insert the X-ray face layer under the edges.

    The viewer adds light (WebGL blend SRC_ALPHA, ONE). The SVG uses ordinary
    alpha instead: mix-blend-mode plus-lighter blanked the whole image when
    Chrome rasterised it, and editors ignore blend modes. With faint layers
    the two agree closely; where many layers overlap the SVG comes out a
    little darker."""
    layer = ET.Element(f'{{{NS}}}g', {'id': 'xray-faces', 'fill': XRAY_FACE, 'stroke': 'none',
                                      'fill-rule': 'nonzero'})
    for alpha, regions in faces:
        group = ET.SubElement(layer, 'g', {'fill-opacity': f'{alpha:.4f}'})
        for loops in regions:
            ET.SubElement(group, 'path', {'d': ' '.join(
                'M' + ' L'.join(f'{x:.4f},{y:.4f}' for x, y in loop) + ' Z' for loop in loops)})
    edges = root.find(f'{{{NS}}}g')
    root.insert(list(root).index(edges), layer)
    edges.set('stroke-opacity', str(XRAY_EDGE_ALPHA))


def svg(paths, title, stroke, background):
    xs = [x for p in paths for x, y in p]
    ys = [y for p in paths for x, y in p]
    x, y = min(xs) - 2, min(ys) - 2
    w, h = max(xs) - x + 2, max(ys) - y + 2
    root = ET.Element(f'{{{NS}}}svg', {'viewBox': f'{x:.5f} {y:.5f} {w:.5f} {h:.5f}',
                          'width': f'{w:.5f}mm', 'height': f'{h:.5f}mm', 'role': 'img'})
    ET.SubElement(root, 'title').text = title
    ET.SubElement(root, 'desc').text = 'Visible STEP edges with OpenCascade hidden-line removal; curve tolerance 0.008 mm. No embedded bitmap.'
    if background != 'transparent':
        ET.SubElement(root, 'rect', dict(x=str(x), y=str(y), width=str(w), height=str(h), fill=background, id='background'))
    group = ET.SubElement(root, 'g', {'id': 'visible-edges', 'fill': 'none', 'stroke': '#464a46',
                'stroke-width': str(stroke), 'stroke-linecap': 'round', 'stroke-linejoin': 'round'})
    for points in paths:
        ET.SubElement(group, 'path', {'d': 'M' + ' L'.join(f'{x:.5f},{y:.5f}' for x, y in points)})
    return ET.tostring(root, encoding='unicode')


def assembly_top(board, stroke, background):
    """Fabrication outlines, physical pads, drills and refs at their saved positions."""
    paths, labels = [], []

    def add(points, fp=None):
        world = [position(fp, x, y) if fp else (x, -y) for x, y in points]
        paths.append([(x, -y) for x, y in world])

    def rounded(w, h, radius):
        pts = []
        for cx, cy, start in [(w/2-radius, h/2-radius, 0), (-w/2+radius, h/2-radius, 90),
                              (-w/2+radius, -h/2+radius, 180), (w/2-radius, -h/2+radius, 270)]:
            pts.extend((cx + radius * math.cos(math.radians(start+i*90/8)),
                        cy + radius * math.sin(math.radians(start+i*90/8))) for i in range(9))
        return pts + pts[:1]

    for edge in board:
        if isinstance(edge, list) and field(edge, 'layer') == ['Edge.Cuts']:
            add([numbers(edge, 'start'), numbers(edge, 'end')])
    for fp in children(board, 'footprint'):
        if field(fp, 'layer') != ['F.Cu']:
            continue
        for item in fp:
            if not isinstance(item, list) or field(item, 'layer') != ['F.Fab']:
                continue
            kind = item[0]
            if kind in ('property', 'fp_text'):
                continue
            if kind == 'fp_line':
                points = [numbers(item, 'start'), numbers(item, 'end')]
            elif kind == 'fp_rect':
                (x, y), (u, v) = numbers(item, 'start'), numbers(item, 'end')
                points = [(x, y), (u, y), (u, v), (x, v), (x, y)]
            elif kind == 'fp_circle':
                x, y = numbers(item, 'center')
                u, v = numbers(item, 'end')
                r = math.hypot(x-u, y-v)
                points = [(x+r*math.cos(a*math.pi/32), y+r*math.sin(a*math.pi/32)) for a in range(65)]
            elif kind == 'fp_poly':
                points = [numbers(['p', n], 'xy') for n in field(item, 'pts')]
                points += points[:1]
            else:
                raise ValueError(f'Unsupported fabrication graphic: {kind}')
            add(points, fp)
        for pad in children(fp, 'pad'):
            if not any(layer in ('F.Cu', '*.Cu') for layer in field(pad, 'layers')) and pad[2] != 'np_thru_hole':
                continue
            w, h = numbers(pad, 'size')
            x, y, *angle = numbers(pad, 'at', (0, 0))
            cx, cy = position(fp, x, y)
            a = math.radians(angle[0] if angle else 0)
            kind = pad[3]
            radius = {'circle': min(w,h)/2, 'oval': min(w,h)/2, 'rect': 0,
                      'roundrect': min(w,h)*numbers(pad, 'roundrect_rratio', (0.25,))[0]}.get(kind)
            if radius is None:
                raise ValueError(f'Unsupported pad shape: {kind}')
            points = rounded(w, h, radius)
            paths.append([(cx+u*math.cos(a)-v*math.sin(a), -cy-u*math.sin(a)-v*math.cos(a)) for u,v in points])
            drill = field(pad, 'drill')
            if drill:
                dw, dh = map(float, drill[1:3]) if drill[0] == 'oval' else (float(drill[0]),)*2
                paths.append([(cx+u*math.cos(a)-v*math.sin(a), -cy-u*math.sin(a)-v*math.cos(a))
                              for u,v in rounded(dw, dh, min(dw,dh)/2)])
        ref = next((n for n in children(fp, 'property') if n[1] == 'Reference'), None)
        if ref is not None and field(ref, 'hide') != ['yes']:
            x, y, *_ = numbers(ref, 'at', (0, 0))
            x, y = position(fp, x, y)
            labels.append((x, -y, reference(fp)))
    root = ET.fromstring(svg(paths, 'Assembly / top', stroke, background))
    root.find(f'{{{NS}}}desc').text = 'KiCad F.Fab outlines, top pads, drills and reference positions; no bitmap.'
    group = ET.SubElement(root, f'{{{NS}}}g', {'id': 'references', 'fill': '#464a46', 'font-family': 'sans-serif',
                  'font-size': '0.6', 'text-anchor': 'middle', 'dominant-baseline': 'middle'})
    for x, y, label in labels:
        ET.SubElement(group, f'{{{NS}}}text', {'x': str(x), 'y': str(y)}).text = label
    return ET.tostring(root, encoding='unicode')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('board', nargs='?', type=Path, help='PCB path; default: parent placement.json or sole PCB')
    parser.add_argument('--out', type=Path, help='Output directory; default: selected PCB folder/renders/svg')
    parser.add_argument('--fetch-models', action='store_true', help='Download missing official KiCad STEP models to the local cache')
    parser.add_argument('--azimuth', type=float, default=-65)
    parser.add_argument('--elevation', type=float, default=38)
    parser.add_argument('--stroke', type=float, default=0.045, help='Line width in mm')
    parser.add_argument('--background', default='#ffffff', help='#RRGGBB or transparent')
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in (args.azimuth, args.elevation, args.stroke)) or not 0 < args.stroke <= 1 or not -90 <= args.elevation <= 90:
        parser.error('Use finite angles, -90 <= elevation <= 90, 0 < stroke <= 1 mm')
    if args.background != 'transparent' and not re.fullmatch(r'#[0-9a-fA-F]{6}', args.background):
        parser.error('background must be #RRGGBB or transparent')
    try:
        board_path = resolve_board(args.board)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    args.out = args.out or board_path.parent / 'renders/svg'
    board = parse_board(board_path.read_text())
    load_occ()
    shape, count = assembly(board, board_path, TOOL_DIR / '.models' / MODEL_REV, args.fetch_models)
    unmodeled = [reference(f) for f in children(board, 'footprint')
                 if 'smd' in field(f, 'attr') and not children(f, 'model') and not f[1].startswith('TestPoint:')]
    if unmodeled:
        print('No 3D model (shown only in assembly top):', ', '.join(unmodeled), flush=True)
    import silk_geometry as silk
    contours = silk.back_contours(board)
    outputs = {'top': assembly_top(board, args.stroke, args.background),
               'bottom': silk.bottom_svg(board,args.stroke,args.background,contours)}
    for name, az, el in [('iso', args.azimuth, args.elevation)]:
        print(f'Projecting {name} (hidden-line removal)…', flush=True)
        paths = project(shape, az, el)
        root = ET.fromstring(svg(paths, f'{board_path.stem} / {name}', args.stroke, args.background))
        silk.append_svg(root,contours,az,el)
        outputs[name] = ET.tostring(root,encoding='unicode')
        print(f'  {len(paths)} visible curves', flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (args.out / f'{name}.svg').write_text(content)
    (args.out / 'index.html').write_text(preview(outputs, board_path.stem, count, unmodeled))
    print('SVG + preview:', args.out.resolve())


def preview(outputs, name, count, unmodeled):
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>PCB → SVG</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4ef;color:#26352c;font:15px system-ui}header{padding:24px 5%;border-bottom:1px solid #d1d6cd;background:#fff}h1{margin:0;font-size:24px}p{color:#647063}main{max-width:1400px;margin:30px auto;padding:0 24px}nav{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin-bottom:24px}label{display:flex;gap:8px;align-items:center}section{display:grid;grid-template-columns:1fr 1fr;gap:24px}article{background:white;border:1px solid #d1d6cd;border-radius:12px;padding:20px}article>svg{display:block;width:100%;height:520px}h2{font-size:16px;margin:0}button{border:0;background:#263f30;color:white;border-radius:6px;padding:10px 16px;cursor:pointer}footer{font-size:13px;margin-top:24px;color:#647063}@media(max-width:800px){section{grid-template-columns:1fr}article>svg{height:400px}}
</style><header><h1>PCB → SVG</h1><p>''' + html.escape(name) + f''' · {count} STEP models · 실제 형상 기반 벡터 선화</p></header>
<main><nav><label>선 굵기 <input id="weight" type="range" min="0.015" max="0.12" step="0.005" value="0.045"><output id="weight-value">0.045 mm</output></label>
<label>선 색 <input id="ink" type="color" value="#464a46"></label><label>배경 <input id="paper" type="color" value="#ffffff"></label><label><input id="clear" type="checkbox">투명 배경</label><label><input id="refs" type="checkbox" checked>참조명</label></nav><section>''' + ''.join(
        f'<article><h2>{label}</h2>{outputs[key]}<button data-view="{key}">SVG 다운로드</button></article>'
        for key, label in [('top', '01 / TOP — 정면'), ('iso', '02 / ISOMETRIC — 입체'), ('bottom','03 / BACK — 뒷면 실크')]) + '''</section>
<footer>STEP 곡선을 0.008 mm 오차로 벡터화합니다. 래스터 이미지 없음. 입체 각도는 render_svg.py --azimuth / --elevation으로 변경합니다.
''' + (f'<p>3D 모델 없음: {html.escape(", ".join(unmodeled))} — 정면도에만 풋프린트를 표시합니다.</p>' if unmodeled else '') + '''</footer></main>
<script>
const views=[...document.querySelectorAll('article>svg')];
const weight=document.getElementById('weight'), ink=document.getElementById('ink'), paper=document.getElementById('paper'), clear=document.getElementById('clear');
weight.value=views[0].querySelector('#visible-edges').getAttribute('stroke-width');
const initial=views[0].querySelector('#background');clear.checked=!initial;if(initial)paper.value=initial.getAttribute('fill');
function update(){document.getElementById('weight-value').textContent=weight.value+' mm';for(const s of views){const g=s.querySelector('#visible-edges');g.setAttribute('stroke-width',weight.value);g.setAttribute('stroke',ink.value);const refs=s.querySelector('#references');if(refs){refs.setAttribute('fill',ink.value);refs.style.display=document.getElementById('refs').checked?'':'none'}for(const p of s.querySelectorAll('#back-silkscreen path'))for(const a of ['fill','stroke'])if(p.getAttribute(a)!=='none')p.setAttribute(a,ink.value);let bg=s.querySelector('#background');if(!bg){bg=document.createElementNS('http://www.w3.org/2000/svg','rect');const [x,y,w,h]=s.getAttribute('viewBox').split(' ');for(const [k,v] of Object.entries({id:'background',x,y,width:w,height:h}))bg.setAttribute(k,v);s.insertBefore(bg,g)}bg.setAttribute('fill',clear.checked?'none':paper.value)}}
for(const input of [weight,ink,paper,clear,document.getElementById('refs')])input.addEventListener('input',update);update();
document.querySelectorAll('button').forEach((b,i)=>b.onclick=()=>{const blob=new Blob([new XMLSerializer().serializeToString(views[i])],{type:'image/svg+xml'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=b.dataset.view+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
</script></html>'''


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ImportError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
