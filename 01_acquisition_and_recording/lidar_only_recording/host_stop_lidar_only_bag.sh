#!/usr/bin/env bash
set -euo pipefail

docker exec \
  -e LIO_BAG_ROOT="${LIO_BAG_ROOT:-}" \
  rk3588_dev bash -lc '/root/fast_livo_runs/scripts/stop_lidar_only_bag.sh "$@"' _ "$@"
