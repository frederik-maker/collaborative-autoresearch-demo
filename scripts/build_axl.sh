#!/usr/bin/env bash
# Clone the AXL P2P node source and produce ./bin/axl.
# Idempotent: skips git clone if vendor/axl already exists.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor/axl"
BIN_DIR="$ROOT/bin"
AXL_REF="${AXL_REF:-main}"

mkdir -p "$BIN_DIR" "$ROOT/vendor"

if [ ! -d "$VENDOR/.git" ]; then
  echo "[build_axl] cloning gensyn-ai/axl @ $AXL_REF -> vendor/axl"
  git clone --depth=1 --branch "$AXL_REF" https://github.com/gensyn-ai/axl.git "$VENDOR"
else
  echo "[build_axl] vendor/axl already present, fetching latest on $AXL_REF"
  (cd "$VENDOR" && git fetch --depth=1 origin "$AXL_REF" && git reset --hard "origin/$AXL_REF")
fi

if ! command -v go >/dev/null 2>&1; then
  echo "[build_axl] ERROR: go not found on PATH. Install Go 1.25+ first." >&2
  exit 1
fi

echo "[build_axl] building node binary"
(cd "$VENDOR" && make build)

cp "$VENDOR/node" "$BIN_DIR/axl"
chmod +x "$BIN_DIR/axl"
echo "[build_axl] wrote $BIN_DIR/axl"
"$BIN_DIR/axl" -h 2>&1 | head -3 || true
