#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/config/project.env"

DATASET="${1:-${DATA_NAME}}"
DISPLAY_VALUE="${DISPLAY:-:0}"
XAUTHORITY_VALUE="${XAUTHORITY:-${HOME}/.Xauthority}"
DOCKER_ARGS=(--rm --net host -e "DISPLAY=${DISPLAY_VALUE}" -e QT_X11_NO_MITSHM=1)
SOFTWARE_RENDERING="${SOFTWARE_RENDERING:-true}"

if [[ "${SOFTWARE_RENDERING}" == "true" ]]; then
  DOCKER_ARGS+=(-e LIBGL_ALWAYS_SOFTWARE=1 -e MESA_LOADER_DRIVER_OVERRIDE=llvmpipe)
elif [[ -e /dev/dri ]]; then
  DOCKER_ARGS+=(--device /dev/dri:/dev/dri)
fi

xhost +local:root >/dev/null 2>&1 || DISPLAY="${DISPLAY_VALUE}" XAUTHORITY="${XAUTHORITY_VALUE}" xhost +local:root >/dev/null 2>&1 || true

docker run "${DOCKER_ARGS[@]}" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "${XAUTHORITY_VALUE}:/root/.Xauthority:ro" \
  -v "${ROOT_DIR}/preprocessed:/preprocessed" \
  --entrypoint /bin/bash \
  "${IMAGE}" -lc "
    set -e
    source /opt/ros/noetic/setup.bash
    source /root/catkin_ws/devel/setup.bash
    rosrun direct_visual_lidar_calibration viewer /preprocessed/${DATASET}
  "
