#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <duration_sec> <run_dir>" >&2
  exit 2
fi

DURATION_SEC="$1"
RUN_DIR="$2"

if ! [[ "$DURATION_SEC" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ABORT] duration must be a positive integer: ${DURATION_SEC}" >&2
  exit 2
fi

sleep "$DURATION_SEC"
LIO_AUTO_STOP=1 exec /root/fast_livo_runs/scripts/stop_lidar_only_bag.sh "$RUN_DIR"
