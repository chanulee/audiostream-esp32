#!/bin/bash
# Regenerate the current LOVELACE board end to end (name / rev: plan_pcb.py).
#   ./make_board.sh            reuse positions.json
#   ./make_board.sh anneal 2   re-run the passive placer with seed 2 first
#   ROUTER=freerouting REROUTE=1 ./make_board.sh
#                              FreeRouting instead of KiCadRoutingTools
#   RENDER=0 ./make_board.sh   skip the renders (renders/latest, ~10 s)
# Needs: KiCad 10 (mounted at /Volumes/KiCad) and, under ../../work/tools, the
# pcb-layout-skill checkout, KiCadRoutingTools (krt/ + krt-venv/) and, for
# ROUTER=freerouting only, FreeRouting + a Java 25 runtime.
set -euo pipefail
cd "$(dirname "$0")"
KICAD=${KICAD:-/Volumes/KiCad/KiCad/KiCad.app/Contents}
PY="$KICAD/Frameworks/Python.framework/Versions/Current/bin/python3"
CLI="$KICAD/MacOS/kicad-cli"
TOOLS=../../work/tools
SKILL=${SKILL:-$TOOLS/pcb-layout-skill/skills/pcb-layout-design}
ROUTER=${ROUTER:-krt}
quiet() { grep -v -e Overflow -e kimath -e wxApp -e 'memory leak' -e '^$' || true; }

if [ "${1:-}" = anneal ]; then
    rm -f positions.json
    "$PY" plan_pcb.py 2>&1 | quiet
    "$PY" autoplace.py 37 41 300000 "${2:-2}" 2>&1 | quiet
fi
"$PY" plan_pcb.py 2>&1 | quiet
python3 "$SKILL/scripts/placement_check.py" placement.json | tail -2
# Netlist against a pin table written from the datasheets, not from plan_pcb.py.
python3 pinout_check.py
# Board name and revision, set once in plan_pcb.py.
NAME=$(python3 -c "import json; print(json.load(open('placement.json'))['board']['name'])")
REV=$(python3 -c "import json; print(json.load(open('placement.json'))['board']['rev'])")
"$PY" build_pcb.py 2>&1 | quiet
# CPL in JLC's rotation / origin convention, parts checked against JLC data.
"$PY" jlc_check.py 2>&1 | quiet
if [ "$ROUTER" = krt ]; then
    # Deterministic: routes from scratch on every run, outer layers only (the
    # inner ones are planes). Three passes: the audio nets on F.Cu only (over
    # the L2 ground plane, never over the L3 digital supply), then power at
    # exactly 0.3 mm on either layer (no neck-down, no size escalation), then
    # everything else at 0.2 mm, which may drop to the board's own floor
    # (0.15 mm) but never below it. The router's output projects (rewritten
    # DRC floors) stay in reports/krt/ and are cleared first: the router reads
    # a sibling project back as its floor.
    rm -rf reports/krt && mkdir -p reports/krt
    KRT="$TOOLS/krt-venv/bin/python $TOOLS/krt/py_router/route.py"
    COMMON=(--clearance 0.16 --via-size 0.6 --via-drill 0.3)
    # Passes that may place vias keep them off same-net SMD pads (paste wicks
    # into an unfilled via; audit_pcb.py checks the result). The audio pass
    # is F.Cu only, places no vias and routes worse with the option.
    NOVIP=(--same-net-pad-clearance 0.1)
    AUDIO=(DAC_L DAC_R LINE_L LINE_R VNEG CAPP CAPM LDOO)
    POWER=(VBUS +5V +5V_DAC +3V3_A SW)
    $KRT "$NAME".kicad_pcb reports/krt/audio.kicad_pcb --nets "${AUDIO[@]}" \
        --layers F.Cu "${COMMON[@]}" --track-width 0.2 --escalation board \
        > reports/krt/audio.log 2>&1
    # Lock the audio copper: the later passes rip earlier routes when they
    # get stuck, and would move DAC_L/R onto B.Cu (over the L3 digital supply).
    # pcbnew's save drops the net-class patterns from the sibling project the
    # next pass reads its clearances from: keep the router's copy.
    cp reports/krt/audio.kicad_pro reports/krt/audio.kicad_pro.keep
    "$PY" -c "import pcbnew as p, sys; b = p.LoadBoard(sys.argv[1]); [t.SetLocked(True) for t in b.GetTracks() if t.GetNetname() in sys.argv[2:]]; b.Save(sys.argv[1])" \
        reports/krt/audio.kicad_pcb "${AUDIO[@]}" 2>&1 | quiet
    mv reports/krt/audio.kicad_pro.keep reports/krt/audio.kicad_pro
    $KRT reports/krt/audio.kicad_pcb reports/krt/power.kicad_pcb --nets "${POWER[@]}" \
        --layers F.Cu B.Cu "${COMMON[@]}" "${NOVIP[@]}" --track-width 0.3 --power-nets "${POWER[@]}" \
        --power-nets-widths 0.3 0.3 0.3 0.3 0.3 --no-power-tap-neckdown \
        --escalation off > reports/krt/power.log 2>&1
    REST=('*' '!GND' '!+3V3_D')
    for n in "${AUDIO[@]}" "${POWER[@]}"; do REST+=("!$n"); done
    $KRT reports/krt/power.kicad_pcb reports/krt/routed.kicad_pcb --nets "${REST[@]}" \
        --layers F.Cu B.Cu "${COMMON[@]}" "${NOVIP[@]}" --track-width 0.2 --escalation board \
        > reports/krt/signal.log 2>&1
    grep -h -E '^  (Single-ended|Multi-point):' reports/krt/{audio,power,signal}.log
    cp reports/krt/routed.kicad_pcb "$NAME".kicad_pcb
    "$PY" finish_pcb.py 2>&1 | quiet
else
    # FreeRouting is not deterministic: keep the checked session unless asked.
    JAVA=$(find "$TOOLS/jre" -path '*Home/bin/java' | head -1)
    if [ "${REROUTE:-0}" = 1 ] || [ ! -f "$NAME".ses ]; then
        "$JAVA" -jar "$TOOLS/freerouting/freerouting-2.5.0.jar" --gui.enabled=false \
            -de "$NAME".dsn -do "$NAME".ses -mp 100 > reports/freerouting.log 2>&1
    fi
    "$PY" finish_pcb.py --ses 2>&1 | quiet
fi
# --exit-code-violations makes any DRC/ERC finding stop the script (pipefail)
# before a release ZIP is written; grep only prints the summary.
"$CLI" pcb drc --format json --schematic-parity --exit-code-violations -o reports/drc.json "$NAME".kicad_pcb | grep Found
"$CLI" sch erc --format json --exit-code-violations -o reports/erc.json "$NAME".kicad_sch | grep Found
"$PY" audit_pcb.py 2>&1 | quiet

# Fabrication release + the skill's file-level checks (SKILL.md section 7).
rm -rf release && mkdir release
"$CLI" pcb export gerbers -o release/ "$NAME".kicad_pcb \
    --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts > /dev/null
"$CLI" pcb export drill --excellon-separate-th -o release/ "$NAME".kicad_pcb > /dev/null
"$CLI" pcb export ipcd356 -o release/"$NAME".d356 "$NAME".kicad_pcb > /dev/null
cp bom.csv cpl.csv release/
"$PY" "$SKILL/scripts/audit_release.py" release --layers 4 2>&1 | tail -2
"$PY" "$SKILL/scripts/gerber_check.py" netcheck release --ipc release/"$NAME".d356 2>&1 | tail -1
"$PY" "$SKILL/scripts/gerber_check.py" render release --out reports/preview 2>&1 | grep -E 'silk|edge min' | head -3
(cd release && zip -q -r ../"$NAME-rev$REV-release.zip" .)
# Visual review: renders/latest (index.html), the previous run in renders/previous.
if [ "${RENDER:-1}" = 1 ]; then
    "$PY" render_board.py 2>&1 | quiet
fi
