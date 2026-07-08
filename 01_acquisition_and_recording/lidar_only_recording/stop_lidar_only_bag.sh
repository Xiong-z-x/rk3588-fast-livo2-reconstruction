#!/usr/bin/env bash
set -uo pipefail

BASE_ROOT="${LIO_BAG_ROOT:-/root/mid360_data/raw_lio_bags}"
if [ "$#" -gt 0 ]; then
  RUN_DIR="$1"
else
  RUN_DIR="$(cat "${BASE_ROOT}/LATEST_RAW_LIO_RUN_DIR" 2>/dev/null || true)"
fi

if [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; then
  echo "[ABORT] run directory was not found; pass it explicitly or start a recording first." >&2
  exit 2
fi

BASE_ROOT="$(realpath -m "$BASE_ROOT")"
RUN_DIR="$(realpath -m "$RUN_DIR")"
case "$RUN_DIR" in
  "$BASE_ROOT"/*) ;;
  *)
    echo "[ABORT] run directory is outside ${BASE_ROOT}: ${RUN_DIR}" >&2
    exit 2
    ;;
esac

LOG_DIR="${RUN_DIR}/logs"
mkdir -p "$LOG_DIR"

process_is_running() {
  local pid="$1"
  local stat
  stat="$(ps -o stat= -p "$pid" 2>/dev/null | awk '{print $1}')"
  [ -n "$stat" ] && [[ "$stat" != *Z* ]]
}

read_pid() {
  local file="$1"
  if [ -f "$file" ]; then
    cat "$file" 2>/dev/null || true
  fi
}

stop_owned_process() {
  local label="$1"
  local pid="$2"
  local wait_seconds="$3"

  if [ -z "$pid" ] || ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    echo "[INFO] ${label}: no valid PID recorded."
    return
  fi
  if ! process_is_running "$pid"; then
    echo "[INFO] ${label}: pid=${pid} is already stopped."
    return
  fi

  echo "[INFO] stopping ${label} pid=${pid} with SIGINT."
  kill -INT "$pid" 2>/dev/null || true
  for _ in $(seq 1 "$wait_seconds"); do
    if ! process_is_running "$pid"; then
      echo "[OK] ${label} stopped."
      return
    fi
    sleep 1
  done

  echo "[WARN] ${label} pid=${pid} did not stop after ${wait_seconds}s; sending SIGTERM."
  kill -TERM "$pid" 2>/dev/null || true
  sleep 2
}

auto_pid="$(read_pid "${RUN_DIR}/auto_stop.pid")"
if [ -n "$auto_pid" ] && [ "$auto_pid" != "$$" ] && process_is_running "$auto_pid"; then
  echo "[INFO] cancelling auto-stop pid=${auto_pid}."
  kill -TERM "$auto_pid" 2>/dev/null || true
fi

bag_pid="$(read_pid "${RUN_DIR}/rosbag.pid")"
stop_owned_process "rosbag" "$bag_pid" 30

launch_pid="$(read_pid "${RUN_DIR}/livox_launch.pid")"
stop_owned_process "Livox roslaunch" "$launch_pid" 20

date +%s >"${RUN_DIR}/stop_epoch"

echo "[INFO] run_dir=${RUN_DIR}"
echo "[INFO] files:"
find "$RUN_DIR" -maxdepth 3 -type f -printf '%p %s bytes\n' | sort

active="$(find "${RUN_DIR}/bags" -maxdepth 1 -type f -name '*.bag.active' -print -quit 2>/dev/null || true)"
bag="$(find "${RUN_DIR}/bags" -maxdepth 1 -type f -name '*.bag' | sort | tail -n 1 || true)"

if [ -n "$active" ]; then
  echo "[WARN] active bag remains and was preserved: ${active}" >&2
  exit 4
fi
if [ -z "$bag" ]; then
  echo "[WARN] no finalized bag exists under ${RUN_DIR}/bags." >&2
  exit 5
fi

set +u
source /opt/ros/noetic/setup.bash
source /root/fast_lio2_ws/devel/setup.bash
set -u
rosbag info "$bag" | tee "${LOG_DIR}/rosbag_info.txt"
touch "${RUN_DIR}/stopped.ok"

echo "[OK] finalized_bag=${bag}"
