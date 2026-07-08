#!/usr/bin/env bash
set -eo pipefail

BASE_ROOT="${RAW_BAG_ROOT:-/root/mid360_data/raw_full_bags}"
EXPLICIT_RUN_DIR=0
if [ "$#" -gt 0 ]; then
  EXPLICIT_RUN_DIR=1
  RUN_DIR="$1"
else
  RUN_DIR="$(cat "${BASE_ROOT}/LATEST_RAW_FULL_RUN_DIR" 2>/dev/null || true)"
fi

if [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; then
  echo "[ABORT] raw bag run directory not found. Pass it explicitly or start a recording first." >&2
  exit 2
fi

PID_FILE="${RUN_DIR}/rosbag.pid"
PREVIEW_PID_FILE="${RUN_DIR}/camera_preview.pid"
LOG_FILE="${RUN_DIR}/logs/rosbag_record.log"

echo "[INFO] run_dir=${RUN_DIR}"

process_is_running() {
  local check_pid="$1"
  local stat
  stat="$(ps -o stat= -p "$check_pid" 2>/dev/null | awk '{print $1}')"
  if [ -z "$stat" ]; then
    return 1
  fi
  case "$stat" in
    *Z*) return 1 ;;
    *) return 0 ;;
  esac
}

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
else
  pid=""
fi

if [ -n "$pid" ] && process_is_running "$pid"; then
  echo "[INFO] stopping rosbag pid=${pid}"
  kill -INT "$pid" || true
else
  if [ "$EXPLICIT_RUN_DIR" -eq 1 ]; then
    echo "[WARN] pid file is missing or process is not alive; explicit run_dir was passed, so broad fallback kill is skipped."
  else
    echo "[WARN] pid file is missing or process is not alive; trying fallback process search."
    pkill -INT -f "rosbag record .*raw_full" || true
  fi
fi

for _ in $(seq 1 30); do
  if [ -n "$pid" ]; then
    if ! process_is_running "$pid"; then
      break
    fi
  elif ! pgrep -af "rosbag record .*raw_full" | grep -v grep >/dev/null; then
    break
  fi
  sleep 1
done

if [ -n "$pid" ] && process_is_running "$pid"; then
  echo "[WARN] rosbag pid=${pid} is still alive after SIGINT; sending SIGTERM."
  kill -TERM "$pid" || true
  sleep 2
elif [ "$EXPLICIT_RUN_DIR" -eq 0 ] && pgrep -af "rosbag record .*raw_full" | grep -v grep >/dev/null; then
  echo "[WARN] rosbag is still alive after SIGINT; sending SIGTERM."
  pkill -TERM -f "rosbag record .*raw_full" || true
  sleep 2
fi

if [ -f "$PREVIEW_PID_FILE" ]; then
  preview_pid="$(cat "$PREVIEW_PID_FILE" 2>/dev/null || true)"
else
  preview_pid=""
fi

if [ -n "$preview_pid" ] && process_is_running "$preview_pid"; then
  echo "[INFO] stopping camera preview pid=${preview_pid}"
  kill -INT "$preview_pid" || true
  sleep 1
  kill -TERM "$preview_pid" 2>/dev/null || true
else
  if [ "$EXPLICIT_RUN_DIR" -eq 0 ]; then
    pkill -TERM -f "image_view.*(/hikrobot_camera/rgb|${RUN_DIR})" || true
  fi
fi

echo "[INFO] files:"
find "$RUN_DIR" -maxdepth 3 -type f -printf "%p %s bytes\n" | sort

echo "[INFO] rosbag log tail:"
tail -80 "$LOG_FILE" 2>/dev/null || true

bag="$(find "$RUN_DIR/bags" -maxdepth 1 -type f -name '*.bag' | sort | tail -1 || true)"
active="$(find "$RUN_DIR/bags" -maxdepth 1 -type f -name '*.bag.active' | sort | tail -1 || true)"

if [ -n "$active" ]; then
  echo "[WARN] active bag remains: ${active}"
  echo "[WARN] Do not delete it; run rosbag reindex if needed."
fi

if [ -n "$bag" ]; then
  echo "[OK] finalized bag=${bag}"
  source /opt/ros/noetic/setup.bash
  rosbag info "$bag" | sed -n '1,180p' || true
else
  echo "[WARN] no finalized .bag found yet."
fi

df -h /root "$BASE_ROOT" || true
