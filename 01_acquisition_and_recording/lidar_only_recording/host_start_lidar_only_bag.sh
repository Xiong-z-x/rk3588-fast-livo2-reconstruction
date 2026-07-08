#!/usr/bin/env bash
set -euo pipefail

RK3588_ROS_CONTAINER="${RK3588_ROS_CONTAINER:-rk3588_dev}"
docker exec \
  -e LIO_BAG_ROOT="${LIO_BAG_ROOT:-}" \
  -e LIO_BAG_DURATION_SEC="${LIO_BAG_DURATION_SEC:-}" \
  "$RK3588_ROS_CONTAINER" bash -lc '/root/fast_livo_runs/scripts/start_lidar_only_bag.sh "$@"' _ "$@"
