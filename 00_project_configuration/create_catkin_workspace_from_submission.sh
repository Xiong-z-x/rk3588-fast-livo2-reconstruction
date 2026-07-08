#!/usr/bin/env bash
# Assemble a ROS1 catkin workspace from this submission package.
#
# Default mode creates symbolic links into the repository so source updates are
# visible immediately. Use --copy for an isolated review workspace.

set -euo pipefail

WORKSPACE="${FAST_LIVO2_WS:-/root/fast_lio2_ws}"
MODE="link"
WITH_CALIBRATION="false"

usage() {
  cat <<'USAGE'
Usage:
  create_catkin_workspace_from_submission.sh [--workspace PATH] [--copy] [--with-calibration]

Options:
  --workspace PATH     Target catkin workspace. Default: /root/fast_lio2_ws
  --copy               Copy source trees instead of creating symbolic links.
  --with-calibration   Also add direct_visual_lidar_calibration source tree.
  -h, --help           Show this help.

The script refuses to overwrite existing package directories.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace)
      WORKSPACE="${2:?missing value for --workspace}"
      shift 2
      ;;
    --copy)
      MODE="copy"
      shift
      ;;
    --with-calibration)
      WITH_CALIBRATION="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$WORKSPACE" || "$WORKSPACE" == "/" ]]; then
  echo "unsafe workspace path: $WORKSPACE" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_ROOT="$REPO_ROOT/07_full_source_code"
WS_SRC="$WORKSPACE/src"

mkdir -p "$WS_SRC"

place_tree() {
  local source_dir="$1"
  local package_dir="$2"
  local target_dir="$WS_SRC/$package_dir"

  if [[ ! -d "$source_dir" ]]; then
    echo "missing source tree: $source_dir" >&2
    exit 1
  fi

  if [[ -e "$target_dir" || -L "$target_dir" ]]; then
    if [[ -L "$target_dir" && "$(readlink "$target_dir")" == "$source_dir" ]]; then
      echo "already linked: $target_dir -> $source_dir"
      return
    fi
    echo "refusing to overwrite existing package path: $target_dir" >&2
    exit 1
  fi

  if [[ "$MODE" == "copy" ]]; then
    cp -a "$source_dir" "$target_dir"
    echo "copied: $package_dir"
  else
    ln -s "$source_dir" "$target_dir"
    echo "linked: $package_dir -> $source_dir"
  fi
}

place_tree "$SRC_ROOT/FAST-LIVO2_elf2_mid360_hik" "FAST-LIVO2"
place_tree "$SRC_ROOT/livox_ros_driver2_elf2_mid360" "livox_ros_driver2"
place_tree "$SRC_ROOT/mvs_ros_driver_elf2_hikrobot" "mvs_ros_driver"

if [[ "$WITH_CALIBRATION" == "true" ]]; then
  place_tree "$SRC_ROOT/direct_visual_lidar_calibration_elf2" "direct_visual_lidar_calibration"
fi

python3 "$REPO_ROOT/06_source_manifests/verify_submission_static.py"

cat <<EOF

Workspace assembled at:
  $WORKSPACE

Next build command:
  cd "$WORKSPACE" && catkin_make

If Livox SDK, Hikrobot MVS SDK or calibration package dependencies are missing,
install those vendor dependencies first, then rerun catkin_make.
EOF
