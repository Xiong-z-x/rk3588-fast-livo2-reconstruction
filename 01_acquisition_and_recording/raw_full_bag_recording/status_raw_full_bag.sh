#!/usr/bin/env bash
set -eo pipefail

BASE_ROOT="${RAW_BAG_ROOT:-/root/mid360_data/raw_full_bags}"

source /opt/ros/noetic/setup.bash
source /root/fast_lio2_ws/devel/setup.bash

echo "=== recorder processes ==="
pgrep -af "rosbag record .*raw_full" || true

echo
echo "=== camera preview processes ==="
pgrep -af "image_view.*hikrobot_camera/rgb|rqt_image_view" || true

echo
echo "=== capture processes ==="
pgrep -af "capture_mid360_hik|livox_ros_driver2_node|grabImgWithTrigger|camera_info_from_image" || true

echo
echo "=== required topics ==="
for topic in /livox/lidar /livox/imu /hikrobot_camera/rgb /hikrobot_camera/camera_info; do
  if timeout 2s rostopic type "$topic" >/tmp/raw_bag_topic_type 2>/tmp/raw_bag_topic_err; then
    echo "${topic} $(cat /tmp/raw_bag_topic_type)"
  else
    echo "${topic} MISSING"
  fi
done
rm -f /tmp/raw_bag_topic_type /tmp/raw_bag_topic_err

echo
echo "=== latest run ==="
latest="$(cat "${BASE_ROOT}/LATEST_RAW_FULL_RUN_DIR" 2>/dev/null || true)"
echo "${latest:-none}"
if [ -n "$latest" ] && [ -d "$latest" ]; then
  find "$latest" -maxdepth 3 -type f -printf "%p %s bytes\n" | sort
  if [ -f "$latest/record_start_epoch" ] && [ -f "$latest/duration_sec" ]; then
    start_epoch="$(cat "$latest/record_start_epoch" 2>/dev/null || echo 0)"
    duration_sec="$(cat "$latest/duration_sec" 2>/dev/null || echo 0)"
    now_epoch="$(date +%s)"
    elapsed=$((now_epoch - start_epoch))
    remain=$((duration_sec - elapsed))
    if [ "$remain" -gt 0 ]; then
      echo
      echo "=== auto-stop countdown ==="
      echo "elapsed=${elapsed}s remaining=${remain}s duration=${duration_sec}s"
    else
      echo
      echo "=== auto-stop countdown ==="
      echo "elapsed=${elapsed}s duration=${duration_sec}s; auto-stop should have fired."
    fi
  fi
  if [ -f "$latest/logs/camera_preview.log" ]; then
    echo
    echo "=== camera preview log tail ==="
    tail -40 "$latest/logs/camera_preview.log" || true
  fi
fi

echo
echo "=== disk ==="
df -h /root "$BASE_ROOT" 2>/dev/null || df -h /root
