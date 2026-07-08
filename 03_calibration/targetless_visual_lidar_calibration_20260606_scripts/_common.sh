#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/config/project.env"

DISPLAY_VALUE="${DISPLAY:-${DISPLAY_FALLBACK:-:1}}"
SOFTWARE_RENDERING="${SOFTWARE_RENDERING:-${SOFTWARE_RENDERING_DEFAULT:-false}}"
CALIB_WS_HOST="${CALIB_WS_HOST:-/home/hyz/livo_workspace/env_ws/calib_ws}"
CALIB_WS_CONTAINER="${CALIB_WS_CONTAINER:-/home/workspace/env_ws/calib_ws}"

if [[ -n "${XAUTHORITY:-}" && -r "${XAUTHORITY}" ]]; then
  XAUTHORITY_VALUE="${XAUTHORITY}"
elif [[ -r "${XAUTHORITY_FALLBACK:-}" ]]; then
  XAUTHORITY_VALUE="${XAUTHORITY_FALLBACK}"
elif [[ -r "${HOME}/.Xauthority" ]]; then
  XAUTHORITY_VALUE="${HOME}/.Xauthority"
else
  XAUTHORITY_VALUE=""
fi

CONTAINER_SETUP="source /opt/ros/noetic/setup.bash && source ${CALIB_WS_CONTAINER}/devel/setup.bash"

docker_base_args() {
  local args=(--rm --net host)

  if [[ "${NVIDIA_GPU:-true}" == "true" ]]; then
    args+=(--gpus all)
    args+=(-e NVIDIA_VISIBLE_DEVICES=all)
    args+=(-e NVIDIA_DRIVER_CAPABILITIES=all)
    args+=(-e __GLX_VENDOR_LIBRARY_NAME=nvidia)
    args+=(-e __NV_PRIME_RENDER_OFFLOAD=1)
  fi

  args+=(-v "${CALIB_WS_HOST}:${CALIB_WS_CONTAINER}:ro")
  printf '%s\n' "${args[@]}"
}

docker_gui_args() {
  local args=(-e "DISPLAY=${DISPLAY_VALUE}" -e QT_X11_NO_MITSHM=1)
  args+=(-v /tmp/.X11-unix:/tmp/.X11-unix:rw)

  if [[ -n "${XAUTHORITY_VALUE}" ]]; then
    args+=(-e XAUTHORITY=/root/.Xauthority)
    args+=(-v "${XAUTHORITY_VALUE}:/root/.Xauthority:ro")
  fi

  if [[ "${SOFTWARE_RENDERING}" == "true" ]]; then
    args+=(-e LIBGL_ALWAYS_SOFTWARE=1 -e MESA_LOADER_DRIVER_OVERRIDE=llvmpipe)
  fi

  printf '%s\n' "${args[@]}"
}

allow_local_x11() {
  DISPLAY="${DISPLAY_VALUE}" XAUTHORITY="${XAUTHORITY_VALUE}" xhost +local:root >/dev/null 2>&1 || true
}
