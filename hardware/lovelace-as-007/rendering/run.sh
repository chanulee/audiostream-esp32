#!/bin/bash
# Resolve the tool location, so launching from another cwd or after moving works.
set -euo pipefail
TOOL_DIR=$(cd "$(dirname "$0")" && pwd)
PYTHON="$TOOL_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    python3 -m venv "$TOOL_DIR/.venv"
fi
if ! "$PYTHON" -c 'import OCP' 2>/dev/null; then
    "$PYTHON" -m pip install -r "$TOOL_DIR/requirements-svg.txt"
fi
exec "$PYTHON" "$TOOL_DIR/svg_viewer.py" --fetch-models "$@"
