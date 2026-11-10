#!/usr/bin/env bash
# Install the Lean 4 toolchain (via elan) and build the kernel library.
set -euo pipefail
cd "$(dirname "$0")/../lean"
if ! command -v lake >/dev/null 2>&1 && [ ! -x "$HOME/.elan/bin/lake" ]; then
  curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none
fi
export PATH="$HOME/.elan/bin:$PATH"
lake build
echo "Kernel built. Start the app with ./run.sh"
