#!/usr/bin/env python3
"""Install and verify the FAST-LIVO2 Mid-360/Hikrobot adaptation files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


FAST_LIVO2_SRC = Path(os.environ.get("FAST_LIVO2_SRC", "/root/fast_lio2_ws/src/FAST-LIVO2"))
REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPT_DIR = REPO_ROOT / "07_full_source_code" / "FAST-LIVO2_project_adaptation"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)


def require_token(path: Path, token: str) -> None:
    text = read(path)
    if token not in text:
        raise RuntimeError(f"{path} does not contain required token: {token}")


def verify_fast_livo2_source(root: Path) -> None:
    required_files = [
        root / "include" / "preprocess.h",
        root / "src" / "preprocess.cpp",
        root / "include" / "LIVMapper.h",
        root / "src" / "LIVMapper.cpp",
        root / "CMakeLists.txt",
        root / "package.xml",
    ]
    for path in required_files:
        require_file(path)

    require_token(root / "include" / "preprocess.h", "livox_ros_driver2/CustomMsg.h")
    require_token(root / "src" / "preprocess.cpp", "livox_ros_driver2::CustomMsg")
    require_token(root / "include" / "LIVMapper.h", "livox_ros_driver2::CustomMsg")
    require_token(root / "src" / "LIVMapper.cpp", "livox_ros_driver2::CustomMsg")
    require_token(root / "CMakeLists.txt", "livox_ros_driver2")
    require_token(root / "package.xml", "livox_ros_driver2")


def install_project_configs(root: Path) -> None:
    config_dir = root / "config"
    launch_dir = root / "launch"
    config_dir.mkdir(parents=True, exist_ok=True)
    launch_dir.mkdir(parents=True, exist_ok=True)

    copies = [
        (ADAPT_DIR / "config" / "mid360.yaml", config_dir / "mid360.yaml"),
        (ADAPT_DIR / "config" / "camera_pinhole_mid360.yaml", config_dir / "camera_pinhole_mid360.yaml"),
        (ADAPT_DIR / "launch" / "mapping_mid360.launch", launch_dir / "mapping_mid360.launch"),
        (ADAPT_DIR / "launch" / "mapping_mid360_only_lio.launch", launch_dir / "mapping_mid360_only_lio.launch"),
    ]
    for src, dst in copies:
        require_file(src)
        shutil.copy2(src, dst)

    require_token(config_dir / "mid360.yaml", "extrin_calib:")
    require_token(config_dir / "mid360.yaml", "Rcl:")
    require_token(config_dir / "mid360.yaml", "Pcl:")
    require_token(launch_dir / "mapping_mid360.launch", "camera_pinhole_mid360.yaml")


def main() -> None:
    verify_fast_livo2_source(FAST_LIVO2_SRC)
    install_project_configs(FAST_LIVO2_SRC)
    print(f"FAST_LIVO2_MID360_ADAPTATION_READY root={FAST_LIVO2_SRC}")


if __name__ == "__main__":
    main()
