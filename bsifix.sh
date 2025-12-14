#!/bin/bash
# Wrapper to run BSIFix with the virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install rich
fi

"$VENV_DIR/bin/python3" "$SCRIPT_DIR/BSIFix.py" "$@"
