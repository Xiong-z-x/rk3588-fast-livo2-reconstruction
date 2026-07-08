#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/scripts/_common.sh"

OUT_NAME="${1:-${DATA_NAME}}"
VOXEL="${VOXEL_RESOLUTION}"
if [[ "${OUT_NAME}" == "${LIGHT_DATA_NAME}" ]]; then
  VOXEL="${LIGHT_VOXEL_RESOLUTION}"
fi

VISUALIZE="${VISUALIZE:-false}"
VIS_FLAG=""
if [[ "${VISUALIZE}" == "true" ]]; then
  VIS_FLAG="-v"
fi

mkdir -p "${ROOT_DIR}/preprocessed/${OUT_NAME}" "${ROOT_DIR}/logs"
LOG="${ROOT_DIR}/logs/01_preprocess_${OUT_NAME}_$(date +%Y%m%d_%H%M%S).log"

{
  echo "OUT_NAME=${OUT_NAME}"
  echo "VOXEL=${VOXEL}"
  echo "IMAGE_TOPIC=${IMAGE_TOPIC}"
  echo "CAMERA_INFO_TOPIC=${CAMERA_INFO_TOPIC}"
  echo "POINTS_TOPIC=${POINTS_TOPIC}"
  echo "CAMERA_INTRINSICS=${CAMERA_INTRINSICS}"
  echo "CAMERA_DISTORTION_COEFFS=${CAMERA_DISTORTION_COEFFS}"
  echo
  DOCKER_ARGS=()
  while IFS= read -r arg; do DOCKER_ARGS+=("${arg}"); done < <(docker_base_args)
  if [[ "${VISUALIZE}" == "true" ]]; then
    allow_local_x11
    while IFS= read -r arg; do DOCKER_ARGS+=("${arg}"); done < <(docker_gui_args)
  fi

  docker run "${DOCKER_ARGS[@]}" \
    -v "${ROOT_DIR}/bags:/bags:ro" \
    -v "${ROOT_DIR}/preprocessed:/preprocessed" \
    --entrypoint /bin/bash \
    "${IMAGE}" -lc "
      set -e
      ${CONTAINER_SETUP}
      rosrun direct_visual_lidar_calibration preprocess \
        --data_path=/bags \
        --dst_path=/preprocessed/${OUT_NAME} \
        --image_topic=${IMAGE_TOPIC} \
        --camera_info_topic=${CAMERA_INFO_TOPIC} \
        --points_topic=${POINTS_TOPIC} \
        --camera_model=${CAMERA_MODEL} \
        --camera_intrinsics=${CAMERA_INTRINSICS} \
        --camera_distortion_coeffs=${CAMERA_DISTORTION_COEFFS} \
        --intensity_channel=${INTENSITY_CHANNEL} \
        --min_distance=${MIN_DISTANCE} \
        --voxel_resolution=${VOXEL} \
        ${VIS_FLAG}
    "
  echo
  echo "== output =="
  ls -lh "${ROOT_DIR}/preprocessed/${OUT_NAME}"
} 2>&1 | tee "${LOG}"

echo "LOG=${LOG}"
