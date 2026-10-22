#!/usr/bin/env python3
"""Run the local SVG/text silkscreen editor with KiCad's bundled Python."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
KICAD = Path(os.environ.get('KICAD', '/Volumes/KiCad/KiCad/KiCad.app/Contents'))


def current_board():
    """The board hardware/versions.json marks current, and its plan header."""
    versions = json.loads((ROOT / 'hardware/versions.json').read_text())['versions']
    folder = ROOT / 'hardware' / next(v['dir'] for v in versions if v['status'] == 'current')
    plan = json.loads((folder / 'placement.json').read_text())['board']
    return folder / f"{plan['name']}.kicad_pcb", plan


def revision(board_path, layout_path):
    return hashlib.sha256(board_path.read_bytes() + b'\0' + (layout_path.read_bytes() if layout_path.exists() else b'')).hexdigest()


def check_layout(board_path, layout, width, height, side):
    """Check an unsaved layout on a temporary PCB; return native silk and markers."""
    import pcbnew as p
    from silkscreen import apply_layout
    if side not in ('F', 'B'):
        raise ValueError('잘못된 면입니다.')
    board = p.LoadBoard(str(board_path))
    apply_layout(board, layout, width, height)
    objects = list(board.GetDrawings())
    for fp in board.GetFootprints():
        objects.extend([fp.Reference(), fp.Value(), *fp.Pads(), *fp.GraphicalItems()])
    objects = {obj.m_Uuid.AsString(): obj for obj in objects}
    with tempfile.TemporaryDirectory(prefix='silk-check-') as temp:
        temp = Path(temp)
        pcb = temp / board_path.name
        project = board_path.with_suffix('.kicad_pro')
        if project.exists():
            shutil.copy2(project, pcb.with_suffix('.kicad_pro'))
        p.SaveBoard(str(pcb), board)
        report, svg = temp / 'drc.json', temp / 'silk.svg'
        cli = str(KICAD / 'MacOS/kicad-cli')
        subprocess.run([cli, 'pcb', 'drc', '--format', 'json', '-o', str(report), str(pcb)],
                       check=True, capture_output=True, timeout=60)
        issues = []
        labels = {'silk_edge_clearance': '보드 가장자리 간섭', 'silk_overlap': '실크끼리 겹침',
                  'silk_over_copper': '패드·솔더마스크 개구부 간섭',
                  'text_height': '글자 높이 규칙 위반', 'text_thickness': '글자 선 두께 규칙 위반'}
        layer = p.F_SilkS if side == 'F' else p.B_SilkS
        for violation in json.loads(report.read_text())['violations']:
            if violation['type'] not in labels:
                continue
            boxes = []
            for item in violation['items']:
                obj = objects.get(item['uuid'])
                if obj is not None and obj.GetLayer() == layer:
                    box = obj.GetBoundingBox()
                    boxes.append([p.ToMM(box.GetLeft()), p.ToMM(box.GetTop()),
                                  p.ToMM(box.GetWidth()), p.ToMM(box.GetHeight())])
            if boxes:
                issues.append(dict(label=labels[violation['type']], boxes=boxes))
        subprocess.run([cli, 'pcb', 'export', 'svg', '--layers', f'{side}.Mask,Edge.Cuts,{side}.SilkS',
                        '--mode-single', '--page-size-mode', '1', '--exclude-drawing-sheet',
                        '-o', str(svg), str(pcb)], check=True, capture_output=True, timeout=30)
        root = ET.fromstring(svg.read_text())
        root.set('viewBox', f'0 0 {width} {height}')
        root.set('width', f'{width}mm')
        root.set('height', f'{height}mm')
        return dict(side=side, svg=ET.tostring(root, encoding='unicode'), issues=issues)


def save_layout(board_path, layout, expected_revision, width, height):
    import pcbnew as p
    from silkscreen import LAYOUT_FILE, apply_layout
    layout_path = board_path.parent / LAYOUT_FILE
    if revision(board_path, layout_path) != expected_revision:
        raise ValueError('다른 프로그램에서 파일이 변경됐습니다. 페이지를 새로고침하세요.')
    if (board_path.parent / ('~' + board_path.stem + '.kicad_pcb.lck')).exists() or (board_path.parent / ('~' + board_path.stem + '.kicad_pro.lck')).exists():
        raise ValueError('KiCad 프로젝트를 닫은 뒤 저장하세요. 열려 있는 편집 내용과 충돌할 수 있습니다.')
    board = p.LoadBoard(str(board_path))
    apply_layout(board, layout, width, height)
    # Keep one recoverable previous state, and stage both outputs before replacing.
    with tempfile.TemporaryDirectory(prefix='.silk-', dir=board_path.parent) as temp:
        temp = Path(temp)
        pcb = temp / board_path.name
        settings = temp / LAYOUT_FILE
        p.SaveBoard(str(pcb), board)
        settings.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
        backup = board_path.with_suffix('.silk-backup.kicad_pcb')
        shutil.copy2(board_path, backup)
        old_layout = layout_path.read_bytes() if layout_path.exists() else None
        if old_layout is not None:
            shutil.copy2(layout_path, layout_path.with_suffix('.json.bak'))
        if revision(board_path, layout_path) != expected_revision:
            raise ValueError('저장 중 외부 변경을 발견했습니다. 새로고침하세요.')
        try:
            os.replace(pcb, board_path)
            os.replace(settings, layout_path)
        except OSError:
            shutil.copy2(backup, board_path)
            if old_layout is None:
                layout_path.unlink(missing_ok=True)
            else:
                layout_path.write_bytes(old_layout)
            raise
    return revision(board_path, layout_path)


def main():
    try:
        import pcbnew as p
    except ImportError:
        python = KICAD / 'Frameworks/Python.framework/Versions/Current/bin/python3'
        if not python.exists():
            raise SystemExit('KiCad 10을 /Volumes/KiCad에 마운트하거나 KICAD 환경변수를 설정하세요.')
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, default=current_board()[0])
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    board_path = args.board.resolve()
    sys.path.insert(0, str(board_path.parent))
    from silkscreen import read_layout, LAYOUT_FILE
    plan = json.loads((board_path.parent / 'placement.json').read_text())
    width, height = plan['board']['w'], plan['board']['h']
    board_id, board_rev = plan['board'].get('id', board_path.stem), plan['board'].get('rev', '')
    token = secrets.token_urlsafe(32)
    web = ROOT / 'tools/silkscreen-editor'
    cache = {}
    asset_root = board_path.parent
    manifest_path = asset_root / 'variants.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    projects = {}
    if manifest:
        for entry in manifest['variants']:
            directory = (asset_root / entry['path']).resolve()
            directory.relative_to(asset_root)
            spec = json.loads((directory / 'placement.json').read_text())
            projects[entry['id']] = (directory / board_path.name, spec)
    else:
        projects['original'] = (board_path, plan)
    default_variant = manifest['default'] if manifest else 'original'

    class Handler(BaseHTTPRequestHandler):
        def send(self, data, content_type='application/json', status=200):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False).encode()
            elif isinstance(data, str):
                data = data.encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            return secrets.compare_digest(self.headers.get('X-Silk-Token', ''), token)

        def project(self):
            parsed = urlsplit(self.path)
            variant = parse_qs(parsed.query).get('variant', [default_variant])[0]
            if variant not in projects:
                raise ValueError('알 수 없는 설계안입니다.')
            self.path = parsed.path
            path, project_plan = projects[variant]
            info = project_plan['board']
            return path, project_plan, info['w'], info['h'], info.get('id', path.stem), info.get('rev', ''), variant

        def do_GET(self):
            try:
                board_path, plan, width, height, board_id, board_rev, variant = self.project()
            except ValueError as exc:
                self.send({'error': str(exc)}, status=400)
                return
            if self.path in ('/', '/editor.js', '/editor.css', '/history.js'):
                name = {'/': 'index.html', '/editor.js': 'editor.js', '/editor.css': 'editor.css', '/history.js': 'history.js'}[self.path]
                mime = {'/': 'text/html; charset=utf-8', '/editor.js': 'text/javascript; charset=utf-8', '/editor.css': 'text/css; charset=utf-8', '/history.js': 'text/javascript; charset=utf-8'}[self.path]
                self.send((web / name).read_bytes(), mime)
                return
            if plan['board'].get('editable_components') and re.fullmatch(r'/assets/[0-9a-f-]{36}-[FB]\.svg', self.path):
                asset = asset_root / self.path.lstrip('/')
                if not asset.is_file():
                    from silkscreen import instance_asset
                    data = instance_asset(board_path.parent, asset.name)
                    if data is None:
                        self.send({'error': 'Not found'}, status=404)
                        return
                    self.send(data, 'image/svg+xml')
                    return
                self.send(asset.read_bytes(), 'image/svg+xml')
                return
            if not self.authorized():
                self.send({'error': '시작 시 출력된 전체 URL로 접속하세요.'}, status=403)
                return
            try:
                if self.path == '/api/state':
                    board = p.LoadBoard(str(board_path))
                    catalog = []
                    if plan['board'].get('editable_components'):
                        from silkscreen import registry
                        catalog = list(registry().values())
                    self.send(dict(width=width, height=height, board=str(board_path),
                                   id=board_id, rev=board_rev,
                                   variants=manifest['variants'] if manifest else [], activeVariant=variant,
                                   notes=plan['board'].get('notes', ''), catalog=catalog,
                                   editableHoles=plan['board'].get('editable_holes', False),
                                   editableComponents=plan['board'].get('editable_components', False),
                                   color=plan['board'].get('color', '#195039'),
                                   revision=revision(board_path, board_path.parent / LAYOUT_FILE),
                                   layout=read_layout(board, board_path.parent, width, height)))
                elif self.path in ('/api/background/F', '/api/background/B', '/api/background/F/copper', '/api/background/B/copper'):
                    side = self.path.split('/')[3]
                    copper = self.path.endswith('/copper')
                    key = (str(board_path), side, copper, hashlib.sha256(board_path.read_bytes()).hexdigest())
                    if key not in cache:
                        with tempfile.TemporaryDirectory() as temp:
                            board = p.LoadBoard(str(board_path))
                            if plan['board'].get('editable_components'):
                                for fp in list(board.GetFootprints()):
                                    board.Delete(fp)
                                for track in list(board.GetTracks()):
                                    board.Delete(track)
                                for drawing in list(board.GetDrawings()):
                                    if drawing.GetLayer() != p.Edge_Cuts or drawing.GetShape() != p.SHAPE_T_RECT:
                                        board.Delete(drawing)
                            if plan['board'].get('editable_holes'):
                                for fp in list(board.GetFootprints()):
                                    if fp.GetReference() in ('M2', 'M2.5', 'M3', 'M4', 'M5'):
                                        board.Delete(fp)
                            for drawing in list(board.GetDrawings()):
                                if drawing.GetLayer() in (p.F_SilkS, p.B_SilkS):
                                    board.Delete(drawing)
                            if copper:
                                for zone in list(board.Zones()):
                                    board.Delete(zone)
                            source, out = Path(temp) / 'base.kicad_pcb', Path(temp) / 'base.svg'
                            p.SaveBoard(str(source), board)
                            layers = f'{side}.Mask,Edge.Cuts,{side}.SilkS'
                            if copper:
                                layers += f',{side}.Cu'
                            subprocess.run([str(KICAD / 'MacOS/kicad-cli'), 'pcb', 'export', 'svg', '--layers', layers,
                                            '--mode-single', '--page-size-mode', '1', '--exclude-drawing-sheet',
                                            '-o', str(out), str(source)], check=True, capture_output=True, timeout=30)
                            svg = ET.fromstring(out.read_text())
                            if plan['board'].get('editable_holes'):
                                for element in svg.iter():
                                    for attribute in ('style', 'stroke', 'fill'):
                                        value = element.get(attribute)
                                        if value:
                                            value = re.sub(r'(stroke|fill):\s*(?:#[0-9a-fA-F]{3,8}|rgb\([^)]*\))', r'\1:#d9b968', value)
                                            if re.fullmatch(r'#[0-9a-fA-F]{3,8}|rgb\([^)]*\)', value):
                                                value = '#d9b968'
                                            element.set(attribute, value)
                            svg.set('viewBox', f'0 0 {width} {height}')
                            svg.set('width', f'{width}mm')
                            svg.set('height', f'{height}mm')
                            cache.clear()
                            cache[key] = ET.tostring(svg)
                    self.send(cache[key], 'image/svg+xml')
                else:
                    self.send({'error': 'Not found'}, status=404)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.send({'error': str(exc)}, status=400)

        def do_POST(self):
            try:
                board_path, plan, width, height, board_id, board_rev, variant = self.project()
            except ValueError as exc:
                self.send({'error': str(exc)}, status=400)
                return
            if self.path not in ('/api/save', '/api/check') or not self.authorized():
                self.send({'error': '저장 권한이 없습니다.'}, status=403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8_000_000:
                    raise ValueError('저장 데이터는 8 MB 이하만 지원합니다.')
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('잘못된 저장 요청입니다.')
                if self.path == '/api/check':
                    if revision(board_path, board_path.parent / LAYOUT_FILE) != request.get('revision'):
                        raise ValueError('PCB 파일이 변경됐습니다. 편집 내용을 저장·백업한 뒤 새로고침하세요.')
                    self.send(check_layout(board_path, request.get('layout'), width, height, request.get('side')))
                    return
                rev = save_layout(board_path, request.get('layout'), request.get('revision'), width, height)
                cache.clear()
                self.send(dict(revision=rev, message='PCB와 silkscreen.json 저장 완료. 제작 전 DRC와 release 재생성이 필요합니다.'))
            except (ValueError, OSError, TypeError, subprocess.SubprocessError) as exc:
                self.send({'error': str(exc)}, status=400)

        def log_message(self, *_):
            pass

    server = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Silkscreen editor: http://127.0.0.1:{server.server_port}/#{token}', flush=True)
    print('Ctrl+C to stop. PCB 파일을 저장할 때 KiCad 프로젝트는 닫아 두세요.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
