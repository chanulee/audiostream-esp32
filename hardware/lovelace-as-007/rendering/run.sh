#!/bin/bash
# Resolve the tool location, so launching from another cwd or after moving works.
set -euo pipefail
TOOL_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON="$TOOL_DIR/.venv/bin/python"
# cadquery-ocp ships wheels for Python 3.10-3.13 only: pick the newest of those.
supported() { "$1" -c 'import sys; sys.exit(not (3, 10) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null; }
if [[ -x "$PYTHON" ]] && ! supported "$PYTHON"; then
    echo "rendering/.venv uses an unsupported Python; recreating it" >&2
    rm -rf "$TOOL_DIR/.venv"
fi
if [[ ! -x "$PYTHON" ]]; then
    BASE=
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null && supported "$candidate"; then
            BASE=$candidate
            break
        fi
    done
    if [[ -z "$BASE" ]]; then
        echo "Python 3.10-3.13 is required (python3 is $(python3 --version 2>&1))" >&2
        exit 1
    fi
    "$BASE" -m venv "$TOOL_DIR/.venv"
fi
if ! "$PYTHON" -c 'import OCP' 2>/dev/null; then
    "$PYTHON" -m pip install -r "$TOOL_DIR/requirements-svg.txt"
fi
exec "$PYTHON" "$TOOL_DIR/svg_viewer.py" --fetch-models "$@"
