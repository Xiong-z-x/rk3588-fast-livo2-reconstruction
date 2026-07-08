#!/usr/bin/env bash
set -euo pipefail

docker exec -i rk3588_dev bash -lc '/root/fast_livo_runs/scripts/status_raw_full_bag.sh "$@"' _ "$@"
