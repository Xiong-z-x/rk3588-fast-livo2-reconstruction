#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/config/project.env"

mkdir -p "${ROOT_DIR}/logs"
LOG="${ROOT_DIR}/logs/00_check_$(date +%Y%m%d_%H%M%S).log"

{
  echo "ROOT_DIR=${ROOT_DIR}"
  echo "IMAGE=${IMAGE}"
  echo "IMAGE_TOPIC=${IMAGE_TOPIC}"
  echo "CAMERA_INFO_TOPIC=${CAMERA_INFO_TOPIC}"
  echo "POINTS_TOPIC=${POINTS_TOPIC}"
  echo
  echo "== host files =="
  ls -lh "${ROOT_DIR}/bags"/*.bag
  echo
  echo "== docker image =="
  docker image inspect "${IMAGE}" >/dev/null
  docker images "${IMAGE}"
  echo
  echo "== rosbag info =="
  docker run --rm \
    -v "${ROOT_DIR}/bags:/bags:ro" \
    --entrypoint /bin/bash \
    "${IMAGE}" -lc '
      set -e
      source /opt/ros/noetic/setup.bash
      source /root/catkin_ws/devel/setup.bash
      echo "direct_visual_lidar_calibration=$(rospack find direct_visual_lidar_calibration)"
      for bag in /bags/*.bag; do
        echo "==== ${bag} ===="
        rosbag info "${bag}" | sed -n "1,80p"
      done
    '
} | tee "${LOG}"

echo "LOG=${LOG}"
