#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/config/project.env"

exec "${ROOT_DIR}/scripts/01_preprocess.sh" "${1:-${LIGHT_DATA_NAME}}"
