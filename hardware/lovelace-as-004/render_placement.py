"""Tiny dependency-free PNG of a placement JSON (courtyards, keep-outs)."""
import json, sys, zlib, struct
d = json.load(open(sys.argv[1])); out = sys.argv[2]; S = 20  # px per mm
b = d['board']; ox, oy = b.get('origin', [0, 0]); W, H = b['w'], b['h']
M = 8 * S; w, h = int(W * S) + 2 * M, int(H * S) + 2 * M
img = [[(250, 250, 250)] * w for _ in range(h)]
def px(x, y): return int((x - ox) * S) + M, int((H - (y - oy)) * S) + M
def rect(x1, y1, x2, y2, col, fill=False):
    a, bb = px(x1, y2), px(x2, y1)
    for yy in range(max(a[1], 0), min(bb[1], h - 1) + 1):
        for xx in range(max(a[0], 0), min(bb[0], w - 1) + 1):
            if fill or yy in (a[1], bb[1]) or xx in (a[0], bb[0]):
                img[yy][xx] = col
COL = {'module': (60, 120, 200), 'ic': (40, 40, 40), 'power': (200, 110, 0),
       'connector': (0, 140, 70), 'passive': (120, 120, 120), 'mech': (150, 0, 150)}
rect(ox, oy, ox + W, oy + H, (0, 0, 0))
for k in d.get('keepouts', []):
    if 'circle' in k:
        cx, cy, r = k['circle']
        for yy in range(h):
            for xx in range(w):
                X = (xx - M) / S + ox; Y = H - (yy - M) / S + oy
                if abs((X - cx) ** 2 + (Y - cy) ** 2 - r * r) < r * 0.08:
                    img[yy][xx] = (220, 0, 220)
for p in d['parts']:
    ww, hh = (p['w'], p['h']) if p['rot'] % 180 == 0 else (p['h'], p['w'])
    x1, y1 = p['x'] - ww / 2, p['y'] - hh / 2
    c = COL.get(p['class'], (0, 0, 0))
    rect(x1, y1, x1 + ww, y1 + hh, tuple(min(255, v + 150) for v in c), True)
    rect(x1, y1, x1 + ww, y1 + hh, c)
raw = b''.join(b'\x00' + bytes(v for px_ in row for v in px_) for row in img)
def chunk(t, data): return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data))
open(out, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))
print('wrote', out, w, h)
