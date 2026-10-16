#!/bin/bash
# Full image set of the current board into renders/extra/: 3D views (six
# sides + six angles), one SVG per layer, all layers in one PDF, a combined
# board SVG and the schematic PDF. renders/latest/ comes from make_board.sh.
#   ./render_extra.sh            high quality (slow, about a minute per view)
#   QUALITY=basic ./render_extra.sh
set -euo pipefail
cd "$(dirname "$0")"
KICAD=${KICAD:-/Volumes/KiCad/KiCad/KiCad.app/Contents}
CLI="$KICAD/MacOS/kicad-cli"
QUALITY=${QUALITY:-high}
NAME=$(python3 -c "import json; print(json.load(open('placement.json'))['board']['name'])")
OUT=renders/extra
rm -rf "$OUT" && mkdir -p "$OUT"
quiet() { grep -v -e Debug -e Overflow -e kimath -e wxApp -e '^$' || true; }

render() { # name, extra kicad-cli render options
    local name=$1; shift
    "$CLI" pcb render -o "$OUT/$name.png" -w 1768 -h 1376 --quality "$QUALITY" \
        --background opaque "$@" "$NAME.kicad_pcb" 2>&1 | quiet
}
for side in top bottom front back left right; do
    render "3d-$side" --side "$side"
done
# Angles: isometric from each corner, a low front view and the underside.
render 3d-angle-1 --perspective --rotate '-45,0,45' --zoom 0.7
render 3d-angle-2 --perspective --rotate '-45,0,-45' --zoom 0.7
render 3d-angle-3 --perspective --rotate '-45,0,135' --zoom 0.7
render 3d-angle-4 --perspective --rotate '-45,0,-135' --zoom 0.7
render 3d-angle-5 --perspective --rotate '-75,0,0' --zoom 0.7
render 3d-angle-6 --perspective --rotate '135,0,30' --zoom 0.7

LAYERS=(F.Cu In1.Cu In2.Cu B.Cu F.Paste F.Mask B.Mask F.Silkscreen B.Silkscreen)
for l in "${LAYERS[@]}"; do
    "$CLI" pcb export svg -o "$OUT/layer-${l/./_}.svg" --layers "$l" \
        --common-layers Edge.Cuts --mode-single --exclude-drawing-sheet \
        --page-size-mode 2 "$NAME.kicad_pcb" 2>&1 | quiet
done
IFS=,; ALL="${LAYERS[*]}"; unset IFS
"$CLI" pcb export pdf -o "$OUT/layers.pdf" --layers "$ALL" \
    --common-layers Edge.Cuts --mode-single "$NAME.kicad_pcb" 2>&1 | quiet
"$CLI" pcb export svg -o "$OUT/$NAME.svg" --layers "F.Cu,F.Silkscreen,F.Mask" \
    --common-layers Edge.Cuts --mode-single --exclude-drawing-sheet \
    --page-size-mode 2 "$NAME.kicad_pcb" 2>&1 | quiet
"$CLI" sch export pdf -o "$OUT/schematic.pdf" "$NAME.kicad_sch" 2>&1 | quiet
ls "$OUT"
