#!/usr/bin/env bash
set -Eeo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <bag_path> <run_dir>" >&2
  exit 2
fi

BAG_PATH="$1"
RUN_DIR="$2"
WS="/root/fast_lio2_ws"
PKG_DIR="$WS/src/FAST-LIVO2"
LOG_DIR="$RUN_DIR/logs"
RESULT_DIR="$RUN_DIR/result"
PCD_SRC_DIR="$PKG_DIR/Log/pcd"
LAUNCH_FILE="$RUN_DIR/mapping_mid360_offline_save.launch"

mkdir -p "$LOG_DIR" "$RESULT_DIR" "$PCD_SRC_DIR"

source /opt/ros/noetic/setup.bash
source "$WS/devel/setup.bash"

if [[ ! -f "$BAG_PATH" ]]; then
  echo "[ERROR] bag not found: $BAG_PATH" >&2
  exit 3
fi

cat > "$LAUNCH_FILE" <<'EOF_LAUNCH'
<launch>
  <rosparam command="load" file="$(find fast_livo)/config/mid360.yaml" />
  <param name="pcd_save/pcd_save_en" value="true" />
  <param name="pcd_save/type" value="0" />
  <param name="pcd_save/interval" value="-1" />
  <param name="pcd_save/filter_size_pcd" value="0.03" />
  <param name="pcd_save/colmap_output_en" value="false" />
  <node launch-prefix="env LD_PRELOAD=/lib/aarch64-linux-gnu/libusb-1.0.so.0" pkg="fast_livo" type="fastlivo_mapping" name="laserMapping" output="screen">
    <rosparam file="$(find fast_livo)/config/camera_pinhole_mid360.yaml" />
  </node>
</launch>
EOF_LAUNCH

echo "[INFO] run_dir=$RUN_DIR"
echo "[INFO] bag=$BAG_PATH"
echo "[INFO] launch=$LAUNCH_FILE"
date '+[INFO] start_time=%F %T %z'

echo "[INFO] stopping stale offline ROS/display processes"
killall -q rviz pcd_to_pointcloud rosbag fastlivo_mapping roscore rosmaster rosout 2>/dev/null || true
sleep 2
killall -q -9 rviz pcd_to_pointcloud rosbag fastlivo_mapping 2>/dev/null || true

echo "[INFO] clearing old FAST-LIVO2 PCD outputs"
find "$PCD_SRC_DIR" -maxdepth 1 -type f \( -name "*.pcd" -o -name "lidar_poses.txt" \) -print -delete 2>/dev/null || true

echo "[INFO] starting roscore"
roscore > "$LOG_DIR/roscore.log" 2>&1 &
ROSCORE_PID=$!
echo "$ROSCORE_PID" > "$RUN_DIR/roscore.pid"
sleep 4

echo "[INFO] setting use_sim_time=true"
rosparam set /use_sim_time true

echo "[INFO] starting FAST-LIVO2"
roslaunch "$LAUNCH_FILE" > "$LOG_DIR/fastlivo2.log" 2>&1 &
FASTLIVO_PID=$!
echo "$FASTLIVO_PID" > "$RUN_DIR/fastlivo2.pid"
sleep 5

echo "[INFO] loaded params snapshot"
rosparam dump "$RUN_DIR/params_loaded.yaml" || true

echo "[INFO] playing rosbag"
rosbag play --clock "$BAG_PATH" --topics /livox/lidar /livox/imu /hikrobot_camera/rgb /hikrobot_camera/camera_info > "$LOG_DIR/rosbag_play.log" 2>&1 &
ROSBAG_PID=$!
echo "$ROSBAG_PID" > "$RUN_DIR/rosbag_play.pid"
set +e
wait "$ROSBAG_PID"
ROSBAG_RC=$?
set -e
echo "[INFO] rosbag play exited rc=$ROSBAG_RC"

echo "[INFO] waiting for FAST-LIVO2 to consume buffered data"
sleep 10

echo "[INFO] stopping FAST-LIVO2 gracefully for savePCD()"
kill -INT "$FASTLIVO_PID" 2>/dev/null || true
for _ in $(seq 1 60); do
  if ! kill -0 "$FASTLIVO_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done
if kill -0 "$FASTLIVO_PID" 2>/dev/null; then
  echo "[WARN] FAST-LIVO2 still alive after SIGINT wait; sending TERM"
  kill -TERM "$FASTLIVO_PID" 2>/dev/null || true
  sleep 3
fi

echo "[INFO] copying PCD outputs"
find "$PCD_SRC_DIR" -maxdepth 1 -type f -print 2>/dev/null | sort | tee "$RUN_DIR/pcd_source_files.txt" || true
cp -f "$PCD_SRC_DIR"/all_raw_points.pcd "$RESULT_DIR/all_raw_points.pcd" 2>/dev/null || true
cp -f "$PCD_SRC_DIR"/all_downsampled_points.pcd "$RESULT_DIR/all_downsampled_points.pcd" 2>/dev/null || true
cp -f "$PCD_SRC_DIR"/lidar_poses.txt "$RESULT_DIR/lidar_poses.txt" 2>/dev/null || true

echo "[INFO] stopping roscore"
kill -INT "$ROSCORE_PID" 2>/dev/null || true
sleep 2
killall -q roscore rosmaster rosout 2>/dev/null || true

echo "[RESULT]"
find "$RESULT_DIR" -maxdepth 1 -type f -printf "%s %p\n" | sort -nr
date '+[INFO] end_time=%F %T %z'

test -s "$RESULT_DIR/all_raw_points.pcd"
