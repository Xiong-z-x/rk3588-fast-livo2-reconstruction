#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/config/project.env"

DATASET="${1:-${DATA_NAME}}"
GUI="${GUI:-true}"
DISPLAY_VALUE="${DISPLAY:-:0}"
XAUTHORITY_VALUE="${XAUTHORITY:-${HOME}/.Xauthority}"
SOFTWARE_RENDERING="${SOFTWARE_RENDERING:-true}"

mkdir -p "${ROOT_DIR}/logs" "${ROOT_DIR}/results"
LOG="${ROOT_DIR}/logs/03_calibrate_${DATASET}_$(date +%Y%m%d_%H%M%S).log"

DOCKER_ARGS=(--rm --net host -v "${ROOT_DIR}/preprocessed:/preprocessed" --entrypoint /bin/bash)
CMD="set -e; source /opt/ros/noetic/setup.bash; source /root/catkin_ws/devel/setup.bash; rosrun direct_visual_lidar_calibration calibrate /preprocessed/${DATASET}"

if [[ "${GUI}" == "false" ]]; then
  CMD="${CMD} --background --auto_quit"
else
  xhost +local:root >/dev/null 2>&1 || DISPLAY="${DISPLAY_VALUE}" XAUTHORITY="${XAUTHORITY_VALUE}" xhost +local:root >/dev/null 2>&1 || true
  DOCKER_ARGS+=(-e "DISPLAY=${DISPLAY_VALUE}" -e QT_X11_NO_MITSHM=1 -v /tmp/.X11-unix:/tmp/.X11-unix:rw -v "${XAUTHORITY_VALUE}:/root/.Xauthority:ro")
  if [[ "${SOFTWARE_RENDERING}" == "true" ]]; then
    DOCKER_ARGS+=(-e LIBGL_ALWAYS_SOFTWARE=1 -e MESA_LOADER_DRIVER_OVERRIDE=llvmpipe)
  elif [[ -e /dev/dri ]]; then
    DOCKER_ARGS+=(--device /dev/dri:/dev/dri)
  fi
fi

docker run "${DOCKER_ARGS[@]}" "${IMAGE}" -lc "${CMD}" 2>&1 | tee "${LOG}"

if [[ -f "${ROOT_DIR}/preprocessed/${DATASET}/calib.json" ]]; then
  cp -f "${ROOT_DIR}/preprocessed/${DATASET}/calib.json" "${ROOT_DIR}/results/calib_result_${DATASET}_$(date +%Y%m%d_%H%M%S).json"
fi

echo "LOG=${LOG}"
