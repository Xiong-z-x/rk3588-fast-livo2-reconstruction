#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/scripts/_common.sh"

DATASET="${1:-${DATA_NAME}}"
GUI="${GUI:-true}"

mkdir -p "${ROOT_DIR}/logs" "${ROOT_DIR}/results"
LOG="${ROOT_DIR}/logs/03_calibrate_${DATASET}_$(date +%Y%m%d_%H%M%S).log"

DOCKER_ARGS=()
while IFS= read -r arg; do DOCKER_ARGS+=("${arg}"); done < <(docker_base_args)
DOCKER_ARGS+=(-v "${ROOT_DIR}/preprocessed:/preprocessed" --entrypoint /bin/bash)
CMD="set -e; ${CONTAINER_SETUP}; rosrun direct_visual_lidar_calibration calibrate --data_path=/preprocessed/${DATASET}"

if [[ "${GUI}" == "false" ]]; then
  CMD="${CMD} --background --auto_quit"
else
  allow_local_x11
  GUI_ARGS=()
  while IFS= read -r arg; do GUI_ARGS+=("${arg}"); done < <(docker_gui_args)
  DOCKER_ARGS+=("${GUI_ARGS[@]}")
fi

docker run "${DOCKER_ARGS[@]}" "${IMAGE}" -lc "${CMD}" 2>&1 | tee "${LOG}"

if [[ -f "${ROOT_DIR}/preprocessed/${DATASET}/calib.json" ]]; then
  cp -f "${ROOT_DIR}/preprocessed/${DATASET}/calib.json" "${ROOT_DIR}/results/calib_result_${DATASET}_$(date +%Y%m%d_%H%M%S).json"
fi

echo "LOG=${LOG}"
