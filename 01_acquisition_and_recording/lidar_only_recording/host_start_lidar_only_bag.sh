#!/usr/bin/env bash
set -euo pipefail

docker exec \
  -e LIO_BAG_ROOT="${LIO_BAG_ROOT:-}" \
  -e LIO_BAG_DURATION_SEC="${LIO_BAG_DURATION_SEC:-}" \
  rk3588_dev bash -lc '/root/fast_livo_runs/scripts/start_lidar_only_bag.sh "$@"' _ "$@"
