#!/usr/bin/env python3
"""Static reproducibility checks for the competition source package."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAST_LIVO = ROOT / "07_full_source_code" / "FAST-LIVO2_elf2_mid360_hik"
HIK = ROOT / "07_full_source_code" / "mvs_ros_driver_elf2_hikrobot"
DASHBOARD = ROOT / "05_realtime_display"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []

    source_text = "\n".join(read(path) for path in FAST_LIVO.rglob("*") if path.is_file() and path.suffix in {".h", ".hpp", ".cpp", ".cmake", ".txt", ".xml", ".launch", ".yaml"})
    old_livox_header = "livox_ros_" + "driver/CustomMsg.h"
    old_livox_namespace = "livox_ros_" + "driver::CustomMsg"
    require(old_livox_header not in source_text, "FAST-LIVO2 must not include the old Livox CustomMsg header", failures)
    require(old_livox_namespace not in source_text, "FAST-LIVO2 must use livox_ros_driver2::CustomMsg", failures)
    require("livox_ros_driver2" in read(FAST_LIVO / "CMakeLists.txt"), "FAST-LIVO2 CMakeLists.txt must depend on livox_ros_driver2", failures)
    require("livox_ros_driver2" in read(FAST_LIVO / "package.xml"), "FAST-LIVO2 package.xml must depend on livox_ros_driver2", failures)

    mid360 = FAST_LIVO / "config" / "mid360.yaml"
    mapping = FAST_LIVO / "launch" / "mapping_mid360.launch"
    cam = FAST_LIVO / "config" / "camera_pinhole_mid360.yaml"
    require(mid360.exists(), "FAST-LIVO2 package must contain config/mid360.yaml", failures)
    require(mapping.exists(), "FAST-LIVO2 package must contain launch/mapping_mid360.launch", failures)
    require(cam.exists(), "FAST-LIVO2 package must contain config/camera_pinhole_mid360.yaml", failures)
    if mid360.exists():
        yaml = read(mid360)
        require("extrin_calib:" in yaml, "mid360.yaml must use extrin_calib namespace", failures)
        require("extrinsic_T:" in yaml and "extrinsic_R:" in yaml, "mid360.yaml must define LiDAR-IMU extrinsic_T and extrinsic_R", failures)
        require("Rcl:" in yaml and "Pcl:" in yaml, "mid360.yaml must define camera Rcl and Pcl", failures)
        require(re.search(r"^\s*extrinsic:\s*$", yaml, re.M) is None, "mid360.yaml must not use the unsupported extrinsic namespace", failures)

    hik_src = read(HIK / "src" / "hikrobot_camera.cpp")
    hik_header = read(HIK / "include" / "hikrobot_camera.hpp")
    require('MV_CC_SetEnumValue(handle, "TriggerMode", 0)' not in hik_header, "Hikrobot driver must not force TriggerMode off", failures)
    require("TriggerSource" in hik_header and "LineSelector" in hik_header, "Hikrobot driver must configure trigger source and line selector", failures)
    require("camera_info_msg.K" in hik_src and "camera_info_msg.P" in hik_src and "camera_info_msg.D" in hik_src, "Hikrobot driver must publish complete CameraInfo K/D/P", failures)
    require("sensor_msgs::image_encodings::RGB8" in hik_src, "Hikrobot image topic must publish RGB8 when topic name is /rgb", failures)

    probe = read(DASHBOARD / "tools" / "rk3588_display_probe.py")
    require("RejectPolicy" in probe, "SSH probe must not auto-trust unknown host keys by default", failures)
    require("validate_container_name" in probe, "SSH probe must validate docker container names", failures)
    require("address:=127.0.0.1" in probe or "bridge_address" in probe, "Foxglove bridge must not bind 0.0.0.0 by default", failures)

    require((DASHBOARD / "tools" / "rk3588_edge_status_server.py").exists(), "Realtime display must include a real edge status backend", failures)
    require((DASHBOARD / "web_dashboard" / "src" / "data" / "liveAdapter.ts").exists(), "Web dashboard must include a live adapter", failures)

    project_scripts = []
    for base in (ROOT / "01_acquisition_and_recording", ROOT / "02_reconstruction_and_mapping"):
        project_scripts.extend(path for path in base.rglob("*.sh") if "tests" not in path.parts)
    project_script_text = "\n".join(read(path) for path in project_scripts)
    unsafe_kill_regex = r"\b(" + "kill" + r"all|p" + r"kill)\b"
    require(re.search(unsafe_kill_regex, project_script_text) is None, "Project runtime scripts must not use global kill helpers", failures)
    unsafe_find_delete = "-" + "delete"
    require(unsafe_find_delete not in project_script_text, "Project runtime scripts must not remove files through find deletion", failures)

    if failures:
        print("STATIC CHECK FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("STATIC CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
