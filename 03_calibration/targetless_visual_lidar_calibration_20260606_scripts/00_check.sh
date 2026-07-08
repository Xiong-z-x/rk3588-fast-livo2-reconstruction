#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/scripts/_common.sh"

mkdir -p "${ROOT_DIR}/logs"
LOG="${ROOT_DIR}/logs/00_check_$(date +%Y%m%d_%H%M%S).log"

{
  echo "ROOT_DIR=${ROOT_DIR}"
  echo "IMAGE=${IMAGE}"
  echo "IMAGE_TOPIC=${IMAGE_TOPIC}"
  echo "CAMERA_INFO_TOPIC=${CAMERA_INFO_TOPIC}"
  echo "POINTS_TOPIC=${POINTS_TOPIC}"
  echo "CALIB_WS_HOST=${CALIB_WS_HOST}"
  echo "CALIB_WS_CONTAINER=${CALIB_WS_CONTAINER}"
  echo "DISPLAY_VALUE=${DISPLAY_VALUE}"
  echo "XAUTHORITY_VALUE=${XAUTHORITY_VALUE:-none}"
  echo "NVIDIA_GPU=${NVIDIA_GPU}"
  echo "SOFTWARE_RENDERING=${SOFTWARE_RENDERING}"
  echo
  echo "== host files =="
  ls -lh "${ROOT_DIR}/bags"/*.bag
  test -d "${CALIB_WS_HOST}"
  test -f "${CALIB_WS_HOST}/devel/setup.bash"
  echo
  echo "== docker image =="
  docker image inspect "${IMAGE}" >/dev/null
  docker images "${IMAGE}"
  echo
  echo "== gpu in container =="
  docker run $(docker_base_args) --entrypoint /bin/bash "${IMAGE}" -lc 'nvidia-smi -L || true'
  echo
  echo "== rosbag info =="
  docker run $(docker_base_args) \
    -v "${ROOT_DIR}/bags:/bags:ro" \
    --entrypoint /bin/bash \
    "${IMAGE}" -lc '
      set -e
      '"${CONTAINER_SETUP}"'
      echo "direct_visual_lidar_calibration=$(rospack find direct_visual_lidar_calibration)"
      rosrun direct_visual_lidar_calibration preprocess --help | sed -n "1,20p"
      for bag in /bags/*.bag; do
        echo "==== ${bag} ===="
        rosbag info "${bag}" | sed -n "1,80p"
      done
    '
} | tee "${LOG}"

echo "LOG=${LOG}"
