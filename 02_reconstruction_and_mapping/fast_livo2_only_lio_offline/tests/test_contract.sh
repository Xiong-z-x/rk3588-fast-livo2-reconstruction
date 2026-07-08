#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${ROOT}/run_fast_livo2_only_lio_offline_bag.sh"
ANALYZER="${ROOT}/analyze_lidar_poses.py"
VIEWER="${ROOT}/create_lidar_only_webgl_viewer.py"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[ -f "$RUNNER" ] || fail "missing offline runner"
[ -f "$ANALYZER" ] || fail "missing pose analyzer"
[ -f "$VIEWER" ] || fail "missing LiDAR-only viewer wrapper"

bash -n "$RUNNER"
python3 -m py_compile "$ANALYZER" "$VIEWER"

grep -q '<param name="common/img_en" value="0" />' "$RUNNER" ||
  fail "ONLY_LIO parameter override is missing"
grep -q 'FAST_LIVO2_PLAY_RATE:-0.5' "$RUNNER" ||
  fail "default playback rate is not 0.5"
grep -q 'FAST_LIVO2_POST_PLAY_WAIT_SEC:-60' "$RUNNER" ||
  fail "default post-play wait is not 60 seconds"
grep -q -- '--topics /livox/lidar /livox/imu' "$RUNNER" ||
  fail "rosbag playback is not limited to LiDAR and IMU"
if grep -q '/hikrobot_camera/' "$RUNNER"; then
  fail "camera topic appears in ONLY_LIO runner"
fi
if grep -Eq 'killall|pkill|find .* -delete' "$RUNNER"; then
  fail "runner contains broad process or file cleanup"
fi
grep -q 'previous_shared_pcd' "$RUNNER" ||
  fail "shared PCD outputs are not backed up"
grep -q 'generate_livox_pose_layers.py' "$RUNNER" ||
  fail "LiDAR-only layer generation is missing"
grep -q 'analyze_lidar_poses.py' "$RUNNER" ||
  fail "pose analysis is missing"
grep -q 'create_lidar_only_webgl_viewer.py' "$RUNNER" ||
  fail "LiDAR-only WebGL generation is missing"
grep -q 'fast_livo2_color' "$VIEWER" ||
  fail "viewer wrapper does not filter the color layer"
grep -q 'wrapAngle' "$VIEWER" ||
  fail "viewer wrapper does not verify unlimited rotation support"
grep -q 'powerPreference' "$VIEWER" ||
  fail "viewer wrapper does not verify high-performance GPU preference"

echo "PASS: ONLY_LIO offline contract"
