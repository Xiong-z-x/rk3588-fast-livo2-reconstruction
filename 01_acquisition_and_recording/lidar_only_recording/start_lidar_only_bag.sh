#!/usr/bin/env bash
set -Eeo pipefail

RUN_ID="${1:-lidar_only_3min_$(date +%Y%m%d_%H%M%S)}"
BASE_ROOT="${LIO_BAG_ROOT:-/root/mid360_data/raw_lio_bags}"
DURATION_SEC="${LIO_BAG_DURATION_SEC:-180}"
RUN_DIR="${BASE_ROOT}/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
BAG_DIR="${RUN_DIR}/bags"
LATEST_FILE="${BASE_ROOT}/LATEST_RAW_LIO_RUN_DIR"

if ! [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "[ABORT] run_id may contain only letters, numbers, dot, underscore, and dash." >&2
  exit 2
fi
if ! [[ "$DURATION_SEC" =~ ^[1-9][0-9]*$ ]]; then
  echo "[ABORT] LIO_BAG_DURATION_SEC must be a positive integer: ${DURATION_SEC}" >&2
  exit 2
fi
if [ -e "$RUN_DIR" ]; then
  echo "[ABORT] run directory already exists: ${RUN_DIR}" >&2
  exit 2
fi

mkdir -p "$LOG_DIR" "$BAG_DIR"

failed_start_cleanup() {
  local rc=$?
  trap - ERR
  echo "[ERROR] start failed with rc=${rc}; stopping only processes owned by ${RUN_DIR}." >&2
  LIO_BAG_ROOT="$BASE_ROOT" \
    /root/fast_livo_runs/scripts/stop_lidar_only_bag.sh "$RUN_DIR" \
    >"${LOG_DIR}/failed_start_cleanup.log" 2>&1 || true
  exit "$rc"
}
trap failed_start_cleanup ERR

source /opt/ros/noetic/setup.bash
source /root/fast_lio2_ws/devel/setup.bash

available_kb="$(df -Pk "$BASE_ROOT" | awk 'NR == 2 {print $4}')"
if ! [[ "$available_kb" =~ ^[0-9]+$ ]] || [ "$available_kb" -lt 2097152 ]; then
  echo "[ABORT] less than 2 GiB is available under ${BASE_ROOT}." >&2
  exit 3
fi

active_conflicts=()
while IFS= read -r pid; do
  [ -n "$pid" ] || continue
  stat="$(ps -o stat= -p "$pid" 2>/dev/null | awk '{print $1}')"
  if [ -n "$stat" ] && [[ "$stat" != *Z* ]]; then
    command_line="$(ps -o args= -p "$pid" 2>/dev/null || true)"
    active_conflicts+=("${pid} ${command_line}")
  fi
done < <(
  pgrep -f '/opt/ros/noetic/bin/rosmaster|/opt/ros/noetic/bin/roslaunch|/opt/ros/noetic/bin/rosbag record|livox_ros_driver2_node|grabImgWithTrigger' ||
    true
)
if [ "${#active_conflicts[@]}" -gt 0 ]; then
  echo "[ABORT] existing ROS acquisition processes must be stopped first:" >&2
  printf '%s\n' "${active_conflicts[@]}" >&2
  exit 4
fi

printf '%s\n' /livox/lidar /livox/imu >"${RUN_DIR}/topics_requested.txt"
printf '%s\n' "$DURATION_SEC" >"${RUN_DIR}/duration_sec"
date +%s >"${RUN_DIR}/start_epoch"

nohup roslaunch rk3588_color_recon capture_mid360_hik.launch \
  record:=false camera_driver:=none start_livox:=true \
  >"${LOG_DIR}/livox_launch.log" 2>&1 </dev/null &
launch_pid=$!
printf '%s\n' "$launch_pid" >"${RUN_DIR}/livox_launch.pid"

for _ in $(seq 1 20); do
  if ! kill -0 "$launch_pid" 2>/dev/null; then
    echo "[ABORT] Livox roslaunch exited during startup." >&2
    tail -80 "${LOG_DIR}/livox_launch.log" >&2 || true
    exit 5
  fi
  if timeout 1 rostopic type /livox/lidar >/dev/null 2>&1 &&
    timeout 1 rostopic type /livox/imu >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for topic in /livox/lidar /livox/imu; do
  if ! timeout 15 rostopic echo -n 1 "${topic}/header" >/dev/null 2>&1; then
    echo "[ABORT] no message received from ${topic}." >&2
    exit 5
  fi
done

nohup rosbag record \
  --buffsize=2048 \
  --chunksize=4096 \
  -O "${BAG_DIR}/raw_lio_${RUN_ID}.bag" \
  /livox/lidar \
  /livox/imu \
  >"${LOG_DIR}/rosbag_record.log" 2>&1 </dev/null &
bag_pid=$!
printf '%s\n' "$bag_pid" >"${RUN_DIR}/rosbag.pid"
sleep 2

if ! kill -0 "$bag_pid" 2>/dev/null; then
  echo "[ABORT] rosbag record exited immediately." >&2
  tail -80 "${LOG_DIR}/rosbag_record.log" >&2 || true
  exit 6
fi

printf '%s\n' "$RUN_DIR" >"$LATEST_FILE"
nohup env LIO_BAG_ROOT="$BASE_ROOT" \
  /root/fast_livo_runs/scripts/auto_stop_lidar_only_bag.sh \
  "$DURATION_SEC" "$RUN_DIR" \
  >"${LOG_DIR}/auto_stop.log" 2>&1 </dev/null &
auto_pid=$!
printf '%s\n' "$auto_pid" >"${RUN_DIR}/auto_stop.pid"

trap - ERR

echo "[OK] LiDAR-only recording started."
echo "[OK] run_id=${RUN_ID}"
echo "[OK] run_dir=${RUN_DIR}"
echo "[OK] duration_sec=${DURATION_SEC}"
echo "[OK] topics=/livox/lidar,/livox/imu"
echo "[OK] auto_stop_pid=${auto_pid}"
echo "[OK] insurance stop: stop_lidar_only_bag"
