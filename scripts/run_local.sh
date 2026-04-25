#!/usr/bin/env bash
# Local one-command launch: ensure deps + AXL binary, then start the web UI.
# The simulation itself is started by clicking the button in the browser.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x bin/axl ]; then
  echo "[run_local] bin/axl missing, building"
  ./scripts/build_axl.sh
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[run_local] WARNING: ANTHROPIC_API_KEY not set; the Start button will refuse." >&2
fi

uv sync
exec uv run python -m sim.server
