#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/scripts/_common.sh"

DATASET="${1:-${DATA_NAME}}"
DOCKER_ARGS=()
while IFS= read -r arg; do DOCKER_ARGS+=("${arg}"); done < <(docker_base_args)
while IFS= read -r arg; do DOCKER_ARGS+=("${arg}"); done < <(docker_gui_args)

allow_local_x11

docker run "${DOCKER_ARGS[@]}" \
  -v "${ROOT_DIR}/preprocessed:/preprocessed" \
  --entrypoint /bin/bash \
  "${IMAGE}" -lc "
    set -e
    ${CONTAINER_SETUP}
    rosrun direct_visual_lidar_calibration viewer --data_path=/preprocessed/${DATASET}
  "
