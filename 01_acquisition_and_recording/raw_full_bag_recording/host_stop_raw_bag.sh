#!/usr/bin/env bash
set -euo pipefail

RK3588_ROS_CONTAINER="${RK3588_ROS_CONTAINER:-rk3588_dev}"
docker exec -i "$RK3588_ROS_CONTAINER" bash -lc '/root/fast_livo_runs/scripts/stop_raw_full_bag.sh "$@"' _ "$@"
