#!/usr/bin/env bash
set -Eeo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <bag_path> <run_dir>" >&2
  exit 2
fi

BAG_PATH="$1"
RUN_DIR="$2"
WS="/root/fast_lio2_ws"
PKG_DIR="$WS/src/FAST-LIVO2"
PCD_SRC_DIR="$PKG_DIR/Log/pcd"
LOG_DIR="$RUN_DIR/logs"
RESULT_DIR="$RUN_DIR/result"
PCD_BACKUP_DIR="$RUN_DIR/previous_shared_pcd"
LAUNCH_FILE="$RUN_DIR/mapping_mid360_only_lio_offline.launch"
PLAY_RATE="${FAST_LIVO2_PLAY_RATE:-0.5}"
POST_PLAY_WAIT_SEC="${FAST_LIVO2_POST_PLAY_WAIT_SEC:-60}"

if [ ! -f "$BAG_PATH" ]; then
  echo "[ABORT] bag not found: ${BAG_PATH}" >&2
  exit 3
fi
if [ -e "$RUN_DIR" ]; then
  echo "[ABORT] run directory already exists: ${RUN_DIR}" >&2
  exit 3
fi
if ! [[ "$PLAY_RATE" =~ ^0\.[0-9]+$|^[1-9][0-9]*(\.[0-9]+)?$ ]]; then
  echo "[ABORT] invalid FAST_LIVO2_PLAY_RATE: ${PLAY_RATE}" >&2
  exit 3
fi
if ! [[ "$POST_PLAY_WAIT_SEC" =~ ^[0-9]+$ ]]; then
  echo "[ABORT] invalid FAST_LIVO2_POST_PLAY_WAIT_SEC: ${POST_PLAY_WAIT_SEC}" >&2
  exit 3
fi

mkdir -p "$LOG_DIR" "$RESULT_DIR" "$PCD_BACKUP_DIR" "$PCD_SRC_DIR"

set +u
source /opt/ros/noetic/setup.bash
source "$WS/devel/setup.bash"
set -u

process_is_running() {
  local pid="$1"
  local stat
  stat="$(ps -o stat= -p "$pid" 2>/dev/null | awk '{print $1}')"
  [ -n "$stat" ] && [[ "$stat" != *Z* ]]
}

stop_owned_process() {
  local label="$1"
  local pid="${2:-}"
  if [ -z "$pid" ] || ! [[ "$pid" =~ ^[0-9]+$ ]] || ! process_is_running "$pid"; then
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
  kill -TERM "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

ROSCORE_PID=""
FASTLIVO_PID=""
ROSBAG_PID=""
cleanup_on_error() {
  local rc=$?
  trap - ERR
  echo "[ERROR] ONLY_LIO run failed rc=${rc}" >&2
  stop_owned_process "rosbag play" "$ROSBAG_PID"
  stop_owned_process "FAST-LIVO2" "$FASTLIVO_PID"
  stop_owned_process "roscore" "$ROSCORE_PID"
  exit "$rc"
}
trap cleanup_on_error ERR

active_conflicts=()
while IFS= read -r pid; do
  [ -n "$pid" ] || continue
  if process_is_running "$pid"; then
    active_conflicts+=("$(ps -o pid=,stat=,args= -p "$pid")")
  fi
done < <(
  pgrep -f '/opt/ros/noetic/bin/rosmaster|/opt/ros/noetic/bin/roslaunch|/opt/ros/noetic/bin/rosbag play|fastlivo_mapping' ||
    true
)
if [ "${#active_conflicts[@]}" -gt 0 ]; then
  printf '[ABORT] active ROS/offline processes:\n%s\n' "${active_conflicts[@]}" >&2
  exit 4
fi

for name in all_raw_points.pcd all_downsampled_points.pcd lidar_poses.txt; do
  if [ -f "$PCD_SRC_DIR/$name" ]; then
    mv "$PCD_SRC_DIR/$name" "$PCD_BACKUP_DIR/$name"
  fi
done

cat >"$LAUNCH_FILE" <<'EOF_LAUNCH'
<launch>
  <rosparam command="load" file="$(find fast_livo)/config/mid360.yaml" />
  <param name="common/img_en" value="0" />
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

echo "[INFO] bag=${BAG_PATH}"
echo "[INFO] run_dir=${RUN_DIR}"
echo "[INFO] mode=ONLY_LIO img_en=0"
echo "[INFO] play_rate=${PLAY_RATE}"
echo "[INFO] post_play_wait_sec=${POST_PLAY_WAIT_SEC}"
date '+[INFO] start_time=%F %T %z'

roscore >"$LOG_DIR/roscore.log" 2>&1 &
ROSCORE_PID=$!
echo "$ROSCORE_PID" >"$RUN_DIR/roscore.pid"
for _ in $(seq 1 20); do
  if rosparam list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
rosparam set /use_sim_time true

roslaunch "$LAUNCH_FILE" >"$LOG_DIR/fastlivo2.log" 2>&1 &
FASTLIVO_PID=$!
echo "$FASTLIVO_PID" >"$RUN_DIR/fastlivo2.pid"
sleep 5
if ! process_is_running "$FASTLIVO_PID"; then
  tail -100 "$LOG_DIR/fastlivo2.log" >&2 || true
  exit 5
fi
if [ "$(rosparam get /common/img_en)" != "0" ]; then
  echo "[ABORT] /common/img_en is not 0" >&2
  exit 5
fi
rosparam dump "$RUN_DIR/params_loaded.yaml"

rosbag play --clock -r "$PLAY_RATE" "$BAG_PATH" --topics /livox/lidar /livox/imu \
  >"$LOG_DIR/rosbag_play.log" 2>&1 &
ROSBAG_PID=$!
echo "$ROSBAG_PID" >"$RUN_DIR/rosbag_play.pid"
set +e
wait "$ROSBAG_PID"
ROSBAG_RC=$?
set -e
ROSBAG_PID=""
if [ "$ROSBAG_RC" -ne 0 ]; then
  echo "[ABORT] rosbag play exited rc=${ROSBAG_RC}" >&2
  exit 6
fi

echo "[INFO] rosbag playback complete; waiting ${POST_PLAY_WAIT_SEC}s"
sleep "$POST_PLAY_WAIT_SEC"

stop_owned_process "FAST-LIVO2" "$FASTLIVO_PID"
FASTLIVO_PID=""

if [ ! -s "$PCD_SRC_DIR/all_raw_points.pcd" ]; then
  echo "[ABORT] FAST-LIVO2 intensity PCD was not generated" >&2
  exit 7
fi
if [ ! -s "$PCD_SRC_DIR/lidar_poses.txt" ]; then
  echo "[ABORT] lidar_poses.txt was not generated" >&2
  exit 7
fi

cp "$PCD_SRC_DIR/all_raw_points.pcd" "$RESULT_DIR/fast_livo2_only_lio_registered_intensity_full.pcd"
cp "$PCD_SRC_DIR/lidar_poses.txt" "$RESULT_DIR/lidar_poses.txt"

stop_owned_process "roscore" "$ROSCORE_PID"
ROSCORE_PID=""

python3 /root/fast_livo2_runs/analyze_lidar_poses.py \
  --poses "$RESULT_DIR/lidar_poses.txt" \
  --output-prefix "$RESULT_DIR/pose_quality" \
  >"$LOG_DIR/pose_analysis.log" 2>&1

python3 /root/fast_livo2_runs/generate_livox_pose_layers.py \
  --bag "$BAG_PATH" \
  --poses "$RESULT_DIR/lidar_poses.txt" \
  --out-dir "$RESULT_DIR" \
  --view-stride 10 \
  --max-pose-dt 0.12 \
  >"$LOG_DIR/generate_livox_pose_layers.log" 2>&1

python3 /root/fast_livo2_runs/create_lidar_only_webgl_viewer.py \
  --result-dir "$RESULT_DIR" \
  --title "new_scene_3min_20260705 ONLY_LIO" \
  >"$LOG_DIR/create_webgl_viewer.log" 2>&1

test -s "$RESULT_DIR/lidar_pose_mapped_height_full.pcd"
test -s "$RESULT_DIR/lidar_pose_mapped_height_view_stride10.pcd"
test -s "$RESULT_DIR/lidar_pose_trajectory_points.pcd"
test -s "$RESULT_DIR/livox_lidar_raw_accum_full.pcd"
test -s "$RESULT_DIR/webgl_viewer/manifest.json"

find "$RESULT_DIR" -maxdepth 2 -type f -printf '%s %p\n' | sort -nr >"$RUN_DIR/result_files.txt"
date '+[INFO] end_time=%F %T %z'
touch "$RUN_DIR/completed.ok"
trap - ERR

echo "[OK] ONLY_LIO offline reconstruction complete"
cat "$RUN_DIR/result_files.txt"
