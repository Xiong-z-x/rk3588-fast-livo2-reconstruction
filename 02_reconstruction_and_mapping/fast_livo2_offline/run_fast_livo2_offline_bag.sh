#!/usr/bin/env bash
set -Eeo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <bag_path> <run_dir>" >&2
  exit 2
fi

BAG_PATH="$1"
RUN_DIR="$2"
WS="${RK3588_WS:-/root/fast_lio2_ws}"
PKG_DIR="$WS/src/FAST-LIVO2"
LOG_DIR="$RUN_DIR/logs"
RESULT_DIR="$RUN_DIR/result"
PCD_SRC_DIR="$PKG_DIR/Log/pcd"
PCD_BACKUP_DIR="$RUN_DIR/previous_shared_pcd"
LAUNCH_FILE="$RUN_DIR/mapping_mid360_offline_save.launch"
PLAY_RATE="${FAST_LIVO2_PLAY_RATE:-0.5}"
POST_PLAY_WAIT_SEC="${FAST_LIVO2_POST_PLAY_WAIT_SEC:-60}"

if [[ ! -f "$BAG_PATH" ]]; then
  echo "[ERROR] bag not found: $BAG_PATH" >&2
  exit 3
fi
if ! [[ "$PLAY_RATE" =~ ^0\.[0-9]+$|^[1-9][0-9]*(\.[0-9]+)?$ ]]; then
  echo "[ERROR] invalid FAST_LIVO2_PLAY_RATE: ${PLAY_RATE}" >&2
  exit 3
fi
if ! [[ "$POST_PLAY_WAIT_SEC" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] invalid FAST_LIVO2_POST_PLAY_WAIT_SEC: ${POST_PLAY_WAIT_SEC}" >&2
  exit 3
fi

mkdir -p "$LOG_DIR" "$RESULT_DIR" "$PCD_SRC_DIR" "$PCD_BACKUP_DIR"

set +u
source /opt/ros/noetic/setup.bash
source "$WS/devel/setup.bash"
set -u

process_is_running() {
  local pid="$1"
  local stat
  stat="$(ps -o stat= -p "$pid" 2>/dev/null | awk '{print $1}')"
  [[ -n "$stat" && "$stat" != *Z* ]]
}

stop_owned_process() {
  local label="$1"
  local pid="${2:-}"
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]] || ! process_is_running "$pid"; then
    return
  fi
  echo "[INFO] stopping ${label} pid=${pid}"
  kill -INT "$pid" 2>/dev/null || true
  for _ in $(seq 1 60); do
    if ! process_is_running "$pid"; then
      wait "$pid" 2>/dev/null || true
      return
    fi
    sleep 1
  done
  echo "[WARN] ${label} pid=${pid} still alive after SIGINT; sending SIGTERM"
  kill -TERM "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

ROSCORE_PID=""
FASTLIVO_PID=""
ROSBAG_PID=""

cleanup_on_error() {
  local rc=$?
  trap - ERR
  echo "[ERROR] FAST-LIVO2 offline run failed rc=${rc}" >&2
  stop_owned_process "rosbag play" "$ROSBAG_PID"
  stop_owned_process "FAST-LIVO2" "$FASTLIVO_PID"
  stop_owned_process "roscore" "$ROSCORE_PID"
  exit "$rc"
}
trap cleanup_on_error ERR

active_conflicts=()
while IFS= read -r pid; do
  [[ -n "$pid" ]] || continue
  if process_is_running "$pid"; then
    active_conflicts+=("$(ps -o pid=,stat=,args= -p "$pid")")
  fi
done < <(
  pgrep -f '/opt/ros/noetic/bin/rosmaster|/opt/ros/noetic/bin/roslaunch|/opt/ros/noetic/bin/rosbag play|fastlivo_mapping' ||
    true
)
if [[ "${#active_conflicts[@]}" -gt 0 ]]; then
  printf '[ABORT] active ROS/offline processes found. Stop them explicitly before running this script:\n%s\n' "${active_conflicts[@]}" >&2
  exit 4
fi

for name in all_raw_points.pcd all_downsampled_points.pcd lidar_poses.txt; do
  if [[ -f "$PCD_SRC_DIR/$name" ]]; then
    mv "$PCD_SRC_DIR/$name" "$PCD_BACKUP_DIR/${name}.$(date +%s)"
  fi
done

cat >"$LAUNCH_FILE" <<'EOF_LAUNCH'
<launch>
  <rosparam command="load" file="$(find fast_livo)/config/mid360.yaml" />
  <param name="pcd_save/pcd_save_en" value="true" />
  <param name="pcd_save/type" value="0" />
  <param name="pcd_save/interval" value="-1" />
  <param name="pcd_save/filter_size_pcd" value="0.03" />
  <param name="pcd_save/colmap_output_en" value="false" />
  <node launch-prefix="env LD_PRELOAD=/lib/aarch64-linux-gnu/libusb-1.0.so.0"
        pkg="fast_livo" type="fastlivo_mapping" name="laserMapping" output="screen">
    <rosparam file="$(find fast_livo)/config/camera_pinhole_mid360.yaml" />
  </node>
</launch>
EOF_LAUNCH

echo "[INFO] run_dir=$RUN_DIR"
echo "[INFO] bag=$BAG_PATH"
echo "[INFO] launch=$LAUNCH_FILE"
echo "[INFO] play_rate=${PLAY_RATE}"
echo "[INFO] post_play_wait_sec=${POST_PLAY_WAIT_SEC}"
date '+[INFO] start_time=%F %T %z'

echo "[INFO] starting roscore"
roscore >"$LOG_DIR/roscore.log" 2>&1 &
ROSCORE_PID=$!
echo "$ROSCORE_PID" >"$RUN_DIR/roscore.pid"
for _ in $(seq 1 20); do
  if rosparam list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[INFO] setting use_sim_time=true"
rosparam set /use_sim_time true

echo "[INFO] starting FAST-LIVO2"
roslaunch "$LAUNCH_FILE" >"$LOG_DIR/fastlivo2.log" 2>&1 &
FASTLIVO_PID=$!
echo "$FASTLIVO_PID" >"$RUN_DIR/fastlivo2.pid"
sleep 5
if ! process_is_running "$FASTLIVO_PID"; then
  tail -120 "$LOG_DIR/fastlivo2.log" >&2 || true
  exit 5
fi

echo "[INFO] loaded params snapshot"
rosparam dump "$RUN_DIR/params_loaded.yaml" || true

echo "[INFO] playing rosbag"
rosbag play --clock -r "$PLAY_RATE" "$BAG_PATH" --topics \
  /livox/lidar \
  /livox/imu \
  /hikrobot_camera/rgb \
  /hikrobot_camera/camera_info \
  >"$LOG_DIR/rosbag_play.log" 2>&1 &
ROSBAG_PID=$!
echo "$ROSBAG_PID" >"$RUN_DIR/rosbag_play.pid"
set +e
wait "$ROSBAG_PID"
ROSBAG_RC=$?
set -e
ROSBAG_PID=""
echo "[INFO] rosbag play exited rc=$ROSBAG_RC"
if [[ "$ROSBAG_RC" -ne 0 ]]; then
  exit 6
fi

echo "[INFO] waiting for FAST-LIVO2 to consume buffered data"
sleep "$POST_PLAY_WAIT_SEC"

echo "[INFO] stopping FAST-LIVO2 gracefully for savePCD()"
stop_owned_process "FAST-LIVO2" "$FASTLIVO_PID"
FASTLIVO_PID=""

echo "[INFO] copying PCD outputs"
find "$PCD_SRC_DIR" -maxdepth 1 -type f -print 2>/dev/null | sort | tee "$RUN_DIR/pcd_source_files.txt" || true
cp -f "$PCD_SRC_DIR"/all_raw_points.pcd "$RESULT_DIR/all_raw_points.pcd" 2>/dev/null || true
cp -f "$PCD_SRC_DIR"/all_downsampled_points.pcd "$RESULT_DIR/all_downsampled_points.pcd" 2>/dev/null || true
cp -f "$PCD_SRC_DIR"/lidar_poses.txt "$RESULT_DIR/lidar_poses.txt" 2>/dev/null || true

echo "[INFO] stopping roscore"
stop_owned_process "roscore" "$ROSCORE_PID"
ROSCORE_PID=""

echo "[RESULT]"
find "$RESULT_DIR" -maxdepth 1 -type f -printf "%s %p\n" | sort -nr
date '+[INFO] end_time=%F %T %z'
trap - ERR

test -s "$RESULT_DIR/all_raw_points.pcd"
