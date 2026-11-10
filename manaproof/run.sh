#!/usr/bin/env bash
# Launch the Manaproof server and web UI (Python 3.9+, no dependencies).
cd "$(dirname "$0")"
export PATH="$HOME/.elan/bin:$PATH"
exec python3 -m engine.server "$@"
