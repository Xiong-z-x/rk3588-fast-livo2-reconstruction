#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

files=(
  host_start_lidar_only_bag.sh
  host_stop_lidar_only_bag.sh
  start_lidar_only_bag.sh
  stop_lidar_only_bag.sh
  auto_stop_lidar_only_bag.sh
)

for file in "${files[@]}"; do
  path="${ROOT}/${file}"
  [ -f "$path" ] || fail "missing ${file}"
  bash -n "$path" || fail "bash syntax invalid: ${file}"
done
for file in host_start_lidar_only_bag.sh host_stop_lidar_only_bag.sh; do
  if grep -Eq 'docker exec[[:space:]]+-i([[:space:]]|$)' "${ROOT}/${file}"; then
    fail "${file} keeps stdin attached with docker exec -i"
  fi
done

grep -q 'LIO_BAG_DURATION_SEC:-180' "${ROOT}/start_lidar_only_bag.sh" ||
  fail "default duration is not 180 seconds"
grep -q 'camera_driver:=none' "${ROOT}/start_lidar_only_bag.sh" ||
  fail "camera_driver is not disabled"
grep -q '/livox/lidar' "${ROOT}/start_lidar_only_bag.sh" ||
  fail "LiDAR topic is not recorded"
grep -q '/livox/imu' "${ROOT}/start_lidar_only_bag.sh" ||
  fail "IMU topic is not recorded"
if grep -Eq '(^|[[:space:]])ping[[:space:]]' "${ROOT}/start_lidar_only_bag.sh"; then
  fail "start script depends on ping, which is absent from the container image"
fi
grep -q 'ps -o stat=' "${ROOT}/start_lidar_only_bag.sh" ||
  fail "start conflict check does not inspect process state"
grep -Eq 'stat.*!=.*Z' "${ROOT}/start_lidar_only_bag.sh" ||
  fail "start conflict check does not ignore zombie processes"

for file in "${files[@]}"; do
  if grep -q '/hikrobot_camera/' "${ROOT}/${file}"; then
    fail "camera topic found in ${file}"
  fi
done

if grep -Eq 'pkill|killall' "${ROOT}/stop_lidar_only_bag.sh"; then
  fail "stop script contains broad process termination"
fi
grep -q 'kill -INT' "${ROOT}/stop_lidar_only_bag.sh" ||
  fail "stop script does not use SIGINT"
grep -q 'set +u' "${ROOT}/stop_lidar_only_bag.sh" ||
  fail "stop script does not disable nounset while sourcing ROS setup"
grep -Eq 'stop_lidar_only_bag\.sh.*RUN_DIR' "${ROOT}/auto_stop_lidar_only_bag.sh" ||
  fail "auto-stop does not pass the explicit run directory"

echo "PASS: lidar-only recording script contract"
