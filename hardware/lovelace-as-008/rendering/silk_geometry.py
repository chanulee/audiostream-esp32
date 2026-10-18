"""PCB-native back silkscreen, including KiCad newstroke text, as vector geometry."""
import json
import math
from functools import lru_cache
import render_svg as r


@lru_cache(maxsize=1)
def glyphs():
    return json.loads((r.TOOL_DIR / 'newstroke_ascii.json').read_text())


def text_paths(item, fp=None):
    text = item[2] if item[0] in ('property', 'fp_text') else item[1]
    effects = r.field(item, 'effects')
    if 'hide' in effects or r.field(item, 'hide') == ['yes']:
        return []
    font = r.field(effects, 'font')
    if r.field(font, 'face') or 'italic' in font or 'bold' in font:
        raise ValueError('Silk supports the default KiCad stroke font without bold/italic')
    sx, sy = r.numbers(font, 'size', (1, 1))
    width = r.numbers(font, 'thickness', (.15,))[0]
    justify = r.field(effects, 'justify')
    mirror = -1 if 'mirror' in justify else 1
    x, y, *angle = r.numbers(item, 'at', (0, 0))
    if fp is not None:
        x, y = r.position(fp, x, y)
        y = -y
    rotation = angle[0] if angle else 0
    if fp is not None and r.field(item,'unlocked') != ['yes']:
        # KiCad PCB_TEXT::GetDrawRotation: footprint text is upright by default.
        while rotation > 90:
            rotation -= 180
        while rotation <= -90:
            rotation += 180
    a = math.radians(-rotation)
    lines = text.split('\n')
    # KiCad 10 default metrics and legacy stroke-font alignment factors.
    interline = sy * 1.68 * .9583
    height = sy * 1.17 + (len(lines) - 1) * interline
    offset_y = sy - width * .052 - (0 if 'top' in justify else height if 'bottom' in justify else height / 2)
    result = []
    for line_index, line in enumerate(lines):
        if any(c not in glyphs() for c in line):
            raise ValueError('Silk text currently supports printable ASCII only')
        advance = sum((ord(glyphs()[c][1]) - ord(glyphs()[c][0])) / 21 * sx for c in line)
        cursor = width / 1.52 if 'left' in justify else -(advance + width / 1.52) if 'right' in justify else -advance / 2
        baseline = offset_y + line_index * interline
        for char in line:
            code = glyphs()[char]
            left = ord(code[0]) - ord('R')
            path = []
            for i in range(2, len(code), 2):
                pair = code[i:i+2]
                if pair == ' R':
                    if len(path) > 1:
                        result.append((path, False, width))
                    path = []
                    continue
                u = mirror * (cursor + (ord(pair[0]) - ord('R') - left) / 21 * sx)
                v = baseline + (ord(pair[1]) - ord('R') - 8) / 21 * sy
                path.append((x + u*math.cos(a) - v*math.sin(a), y + u*math.sin(a) + v*math.cos(a)))
            if len(path) > 1:
                result.append((path, False, width))
            cursor += (ord(code[1]) - ord(code[0])) / 21 * sx
    return result


def back_contours(board):
    result = []
    for parent in [None, *r.children(board, 'footprint')]:
        for item in board if parent is None else parent:
            if not isinstance(item, list) or r.field(item, 'layer') != ['B.SilkS']:
                continue
            kind = item[0]
            if kind in ('gr_text', 'fp_text', 'property'):
                result.extend(text_paths(item, parent))
                continue
            width = r.numbers(r.field(item, 'stroke'), 'width', (.12,))[0]
            fill = r.field(item, 'fill') == ['yes']
            if kind.endswith('_poly'):
                points = [r.numbers(['p', n], 'xy') for n in r.field(item, 'pts')]
                points += points[:1]
            elif kind.endswith('_line'):
                points = [r.numbers(item, 'start'), r.numbers(item, 'end')]
            elif kind.endswith('_rect'):
                (x, y), (u, v) = r.numbers(item, 'start'), r.numbers(item, 'end')
                points = [(x,y), (u,y), (u,v), (x,v), (x,y)]
            elif kind.endswith('_circle'):
                x, y = r.numbers(item, 'center')
                u, v = r.numbers(item, 'end')
                radius = math.hypot(x-u, y-v)
                points = [(x + radius*math.cos(i*math.pi/32), y + radius*math.sin(i*math.pi/32)) for i in range(65)]
            else:
                raise ValueError(f'Unsupported back silkscreen graphic: {kind}')
            if parent is not None:
                points = [(x,-y) for x,y in (r.position(parent,*p) for p in points)]
            result.append((points, fill, width))
    return result


def append_svg(root, contours, azimuth, elevation, ink='#464a46', camera_center=(0,0,0), focus=None):
    if (focus is None and elevation >= 0) or (focus is not None and camera_center[2]+focus*math.sin(math.radians(elevation)) >= -.01):
        return
    if focus is not None:
        # Perspective is projective, not affine: turn ink strokes into faces first.
        coords = triangles(contours)
        view = r.projector(azimuth,elevation,camera_center,focus)
        group = r.ET.SubElement(root,f'{{{r.NS}}}g',{'id':'back-silkscreen','fill':ink})
        for i in range(0,len(coords),9):
            points = [view.Project(r.gp.gp_Pnt(*coords[j:j+3])) for j in range(i,i+9,3)]
            r.ET.SubElement(group,f'{{{r.NS}}}path',{'d':'M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y,_ in points)+' Z'})
        return
    az, el = map(math.radians, (azimuth, elevation))
    # Affine projection of PCB screen coordinates (x,-y,-0.01) into the camera plane.
    matrix = (-math.sin(az), math.sin(el)*math.cos(az), -math.cos(az),
              -math.sin(el)*math.sin(az), 0, .01*math.cos(el))
    group = r.ET.SubElement(root, f'{{{r.NS}}}g', {'id': 'back-silkscreen',
                           'transform': 'matrix('+' '.join(str(v) for v in matrix)+')',
                           'stroke-linecap': 'round', 'stroke-linejoin': 'round'})
    for points, fill, width in contours:
        r.ET.SubElement(group, f'{{{r.NS}}}path', {'d': 'M'+' L'.join(f'{x:.6f},{y:.6f}' for x,y in points)+(' Z' if fill else ''),
                       'fill': ink if fill else 'none', 'stroke': 'none' if fill else ink, 'stroke-width': str(width)})


def triangles(contours):
    """Ink faces in world coordinates; the live viewer's depth buffer hides the far side."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    output = []

    def polygon(points):
        if len(points) < 3:
            return
        wire = BRepBuilderAPI_MakePolygon()
        for x,y in points:
            wire.Add(r.gp.gp_Pnt(x, -y, -.01))
        wire.Close()
        face = BRepBuilderAPI_MakeFace(wire.Wire()).Face()
        BRepMesh_IncrementalMesh(face, .01)
        loc = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, loc)
        if mesh is None:
            raise ValueError('Cannot triangulate silkscreen')
        for i in range(1, mesh.NbTriangles()+1):
            for index in mesh.Triangle(i).Get():
                p = mesh.Node(index).Transformed(loc.Transformation())
                output.extend((p.X(),p.Y(),p.Z()))

    for points, fill, width in contours:
        if fill:
            polygon(points[:-1] if points[0] == points[-1] else points)
        else:
            radius = width/2
            for (x,y),(u,v) in zip(points,points[1:]):
                length = math.hypot(u-x,v-y)
                if length < 1e-9:
                    continue
                dx,dy = -(v-y)/length*radius,(u-x)/length*radius
                polygon([(x+dx,y+dy),(u+dx,v+dy),(u-dx,v-dy),(x-dx,y-dy)])
            for x,y in points:
                polygon([(x+radius*math.cos(i*math.pi/6),y+radius*math.sin(i*math.pi/6)) for i in range(12)])
    return output


def bottom_svg(board, stroke, background, contours):
    paths = []
    outline = [n for n in board if isinstance(n,list) and r.field(n,'layer') == ['Edge.Cuts']]
    xs = [r.numbers(n,k)[0] for n in outline for k in ('start','end')]
    mirror_x = min(xs)+max(xs)
    for item in outline:
        paths.append([(mirror_x-x,y) for x,y in (r.numbers(item,'start'),r.numbers(item,'end'))])
    for fp in r.children(board,'footprint'):
        for pad in r.children(fp,'pad'):
            drill = r.field(pad,'drill')
            x,y,*angle = r.numbers(pad,'at',(0,0))
            x,y = r.position(fp,x,y)
            if drill and drill[0] == 'oval':
                w,h = map(float,drill[1:3])
                radius,span = min(w,h)/2,abs(w-h)
                a = math.radians((angle[0] if angle else 0)+(90 if h>w else 0))
                points = []
                for center,start in ((span/2,-90),(-span/2,90)):
                    for i in range(33):
                        t = math.radians(start+i*180/32)
                        u,v = center+radius*math.cos(t),radius*math.sin(t)
                        points.append((mirror_x-x-u*math.cos(a)+v*math.sin(a),-y-u*math.sin(a)-v*math.cos(a)))
                paths.append(points+points[:1])
                continue
            elif drill:
                radius = float(drill[0])/2
            elif r.field(fp,'layer') == ['B.Cu'] and pad[3] == 'circle':
                radius = r.numbers(pad,'size')[0]/2
            else:
                continue
            paths.append([(mirror_x-x+radius*math.cos(i*math.pi/32),-y+radius*math.sin(i*math.pi/32)) for i in range(65)])
    root = r.ET.fromstring(r.svg(paths,'Back / silkscreen + test pads',stroke,background))
    append_svg(root,contours,90,-90)
    group = root.find(f'{{{r.NS}}}g[@id="back-silkscreen"]')
    group.set('transform',f'matrix(-1 0 0 1 {mirror_x} 0)')
    root.find(f'{{{r.NS}}}desc').text = 'PCB-native B.SilkS polygons and KiCad stroke text, mirrored for viewing from outside the back.'
    return r.ET.tostring(root,encoding='unicode')
