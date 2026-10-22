#!/usr/bin/env python3
"""Write ui.html: Figma loads one HTML file, so the web editor's stencil
code (SVG cleaning and pixel-to-rectangle merge) is copied in verbatim."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDITOR = HERE.parent / 'silkscreen-editor/editor.js'


def stencil():
    source = EDITOR.read_text()
    return source[source.index('function maskRectangles('):source.index('async function rasterize(')].rstrip()


def build():
    return (HERE / 'ui.template.html').read_text().replace('/*STENCIL*/', stencil())


if __name__ == '__main__':
    (HERE / 'ui.html').write_text(build())
