#!/usr/bin/env bash
set -euo pipefail

docker_tty=(-i)
if [ -t 0 ]; then
  docker_tty=(-it)
fi

docker exec "${docker_tty[@]}" \
  -e RAW_BAG_ROOT="${RAW_BAG_ROOT:-}" \
  -e RAW_BAG_PREVIEW="${RAW_BAG_PREVIEW:-}" \
  -e RAW_BAG_PREVIEW_TOPIC="${RAW_BAG_PREVIEW_TOPIC:-}" \
  -e RAW_BAG_DURATION_SEC="${RAW_BAG_DURATION_SEC:-}" \
  -e RAW_BAG_CONFIRM_START="${RAW_BAG_CONFIRM_START:-}" \
  -e RAW_BAG_START_WORD="${RAW_BAG_START_WORD:-}" \
  -e DISPLAY="${DISPLAY:-:0}" \
  rk3588_dev bash -lc '/root/fast_livo_runs/scripts/start_raw_full_bag.sh "$@"' _ "$@"
