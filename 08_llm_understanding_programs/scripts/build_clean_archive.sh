#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT="${1:-${ROOT_DIR}_clean.zip}"

cd "$(dirname "$ROOT_DIR")"
rm -f "$OUTPUT"
find "$(basename "$ROOT_DIR")" -name ".DS_Store" -delete
find "$(basename "$ROOT_DIR")" -type d -name "__pycache__" -prune -exec rm -rf {} +
zip -r "$OUTPUT" "$(basename "$ROOT_DIR")" \
  -x "__MACOSX/*" \
  -x "*/__MACOSX/*" \
  -x "*/node_modules/*" \
  -x "*/dist/*" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x "*/.DS_Store"

echo "$OUTPUT"
