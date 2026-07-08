#!/usr/bin/env bash
set -eo pipefail

RUN_ID="${1:-raw_full_$(date +%Y%m%d_%H%M%S)}"
BASE_ROOT="${RAW_BAG_ROOT:-/root/mid360_data/raw_full_bags}"
RUN_DIR="${BASE_ROOT}/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
BAG_DIR="${RUN_DIR}/bags"
PID_FILE="${RUN_DIR}/rosbag.pid"
PREVIEW_PID_FILE="${RUN_DIR}/camera_preview.pid"
LATEST_FILE="${BASE_ROOT}/LATEST_RAW_FULL_RUN_DIR"
TOPICS_FILE="${RUN_DIR}/topics.txt"
PREVIEW_ENABLE="${RAW_BAG_PREVIEW:-1}"
PREVIEW_TOPIC="${RAW_BAG_PREVIEW_TOPIC:-/hikrobot_camera/rgb}"
DURATION_SEC="${RAW_BAG_DURATION_SEC:-180}"
CONFIRM_START="${RAW_BAG_CONFIRM_START:-1}"
START_WORD="${RAW_BAG_START_WORD:-start}"

cleanup_started_preview() {
  if [ ! -f "$PREVIEW_PID_FILE" ]; then
    return
  fi
  local preview_pid
  preview_pid="$(cat "$PREVIEW_PID_FILE" 2>/dev/null || true)"
  if [ -n "$preview_pid" ] && kill -0 "$preview_pid" 2>/dev/null; then
    kill -INT "$preview_pid" 2>/dev/null || true
    sleep 1
    kill -TERM "$preview_pid" 2>/dev/null || true
  fi
}

cleanup_unrecorded_run_dir() {
  case "$RUN_DIR" in
    "$BASE_ROOT"/*) ;;
    *) return ;;
  esac
  if find "$BAG_DIR" -maxdepth 1 -type f \( -name '*.bag' -o -name '*.bag.active' \) 2>/dev/null | grep -q .; then
    return
  fi
  rm -rf "$RUN_DIR"
}

source /opt/ros/noetic/setup.bash
source /root/fast_lio2_ws/devel/setup.bash

mkdir -p "$LOG_DIR" "$BAG_DIR"

if ! [[ "$DURATION_SEC" =~ ^[0-9]+$ ]]; then
  echo "[ABORT] RAW_BAG_DURATION_SEC must be an integer number of seconds, got: ${DURATION_SEC}" >&2
  exit 2
fi

if [ "$DURATION_SEC" -eq 0 ]; then
  echo "[WARN] RAW_BAG_DURATION_SEC=0 disables auto-stop. Use stop_raw_bag manually." >&2
fi

if pgrep -af "rosbag record .*raw_full" | grep -v grep >/dev/null; then
  echo "[ABORT] raw_full rosbag record already appears to be running:" >&2
  pgrep -af "rosbag record .*raw_full" | grep -v grep >&2 || true
  exit 2
fi

required_topics=(
  /livox/lidar
  /livox/imu
  /hikrobot_camera/rgb
  /hikrobot_camera/camera_info
)

missing=0
for topic in "${required_topics[@]}"; do
  if ! timeout 3s rostopic type "$topic" > "${RUN_DIR}/.type.out" 2> "${RUN_DIR}/.type.err"; then
    echo "[ABORT] missing required topic: ${topic}" >&2
    cat "${RUN_DIR}/.type.err" >&2 || true
    missing=1
  else
    echo "${topic} $(cat "${RUN_DIR}/.type.out")"
  fi
done
rm -f "${RUN_DIR}/.type.out" "${RUN_DIR}/.type.err"

if [ "$missing" -ne 0 ]; then
  echo "[ABORT] Start capture first, then run this recorder again." >&2
  cleanup_unrecorded_run_dir
  exit 3
fi

rostopic list | sort > "$TOPICS_FILE" || true

echo "[INFO] run_id=${RUN_ID}"
echo "[INFO] run_dir=${RUN_DIR}"
echo "[INFO] bag=${BAG_DIR}/raw_full_${RUN_ID}.bag"
echo "[INFO] this script records raw input topics only; FAST-LIVO is not started."
echo "[INFO] required topics passed. Opening preview before recording."
if [ "$DURATION_SEC" -gt 0 ]; then
  echo "[INFO] auto-stop enabled after ${DURATION_SEC}s."
else
  echo "[INFO] auto-stop disabled; stop manually with stop_raw_bag."
fi

if [ "$PREVIEW_ENABLE" != "0" ]; then
  if pgrep -af "image_view.*${PREVIEW_TOPIC}" | grep -v grep >/dev/null; then
    echo "[INFO] camera preview already appears to be running for ${PREVIEW_TOPIC}."
  elif rospack find image_view >/dev/null 2>&1; then
    export DISPLAY="${DISPLAY:-:0}"
    echo "[INFO] starting camera preview on DISPLAY=${DISPLAY}, topic=${PREVIEW_TOPIC}"
    nohup rosrun image_view image_view image:="${PREVIEW_TOPIC}" _image_transport:=raw \
      > "${LOG_DIR}/camera_preview.log" 2>&1 &
    preview_pid=$!
    echo "$preview_pid" > "$PREVIEW_PID_FILE"
    sleep 2
    if kill -0 "$preview_pid" 2>/dev/null; then
      echo "[OK] camera preview started, pid=${preview_pid}"
    else
      echo "[WARN] camera preview exited immediately. Recording will continue. Log:" >&2
      tail -60 "${LOG_DIR}/camera_preview.log" >&2 || true
    fi
  else
    echo "[WARN] image_view is not available; recording without preview." >&2
  fi
else
  echo "[INFO] camera preview disabled by RAW_BAG_PREVIEW=0."
fi

if [ "$CONFIRM_START" != "0" ]; then
  echo
  echo "[WAIT] Adjust the camera view now."
  echo "[WAIT] Type '${START_WORD}' and press Enter to start rosbag recording."
  echo "[WAIT] Type 'q' and press Enter to cancel and close the preview."
  if [ ! -t 0 ]; then
    echo "[ABORT] stdin is not interactive. Re-run from an SSH terminal, or set RAW_BAG_CONFIRM_START=0." >&2
    cleanup_started_preview
    cleanup_unrecorded_run_dir
    exit 5
  fi
  read -r answer
  case "$answer" in
    "$START_WORD"|START|Start|s|S)
      echo "[INFO] start command accepted."
      ;;
    q|Q|quit|QUIT|cancel|CANCEL)
      echo "[INFO] recording cancelled by user; closing preview."
      cleanup_started_preview
      cleanup_unrecorded_run_dir
      exit 0
      ;;
    *)
      echo "[ABORT] expected '${START_WORD}', got '${answer}'. Closing preview." >&2
      cleanup_started_preview
      cleanup_unrecorded_run_dir
      exit 5
      ;;
  esac
else
  echo "[INFO] RAW_BAG_CONFIRM_START=0, starting recording without interactive confirmation."
fi

echo "$RUN_DIR" > "$LATEST_FILE"
date +%s > "${RUN_DIR}/record_start_epoch"

nohup rosbag record \
  --buffsize=2048 \
  --chunksize=4096 \
  -O "${BAG_DIR}/raw_full_${RUN_ID}.bag" \
  /livox/lidar \
  /livox/imu \
  /hikrobot_camera/rgb \
  /hikrobot_camera/camera_info \
  > "${LOG_DIR}/rosbag_record.log" 2>&1 &

pid=$!
echo "$pid" > "$PID_FILE"
sleep 2

if ! kill -0 "$pid" 2>/dev/null; then
  echo "[ABORT] rosbag record exited immediately. Log:" >&2
  tail -80 "${LOG_DIR}/rosbag_record.log" >&2 || true
  cleanup_started_preview
  exit 4
fi

echo "[OK] raw full bag recording started."
echo "[OK] pid=${pid}"
echo "[OK] stop with: stop_raw_bag"
echo "[OK] log=${LOG_DIR}/rosbag_record.log"
if [ -f "$PREVIEW_PID_FILE" ]; then
  echo "[OK] preview_log=${LOG_DIR}/camera_preview.log"
fi

if [ "$DURATION_SEC" -gt 0 ]; then
  echo "$DURATION_SEC" > "${RUN_DIR}/duration_sec"
  nohup bash -c '
    duration_sec="$1"
    run_dir="$2"
    log_file="$3"
    sleep "$duration_sec"
    /root/fast_livo_runs/scripts/stop_raw_full_bag.sh "$run_dir" >> "$log_file" 2>&1
  ' _ "$DURATION_SEC" "$RUN_DIR" "${LOG_DIR}/auto_stop.log" >/dev/null 2>&1 &
  echo "$!" > "${RUN_DIR}/auto_stop.pid"
  echo "[OK] auto_stop_pid=$(cat "${RUN_DIR}/auto_stop.pid")"
  echo "[OK] auto_stop_log=${LOG_DIR}/auto_stop.log"
fi
