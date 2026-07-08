#!/usr/bin/env bash
set -euo pipefail

docker exec -i rk3588_dev bash -lc '/root/fast_livo_runs/scripts/stop_raw_full_bag.sh "$@"' _ "$@"
