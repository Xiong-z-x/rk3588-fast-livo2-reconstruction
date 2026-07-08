#!/usr/bin/env python3
"""Static reproducibility checks for the competition source package."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAST_LIVO = ROOT / "07_full_source_code" / "FAST-LIVO2_elf2_mid360_hik"
HIK = ROOT / "07_full_source_code" / "mvs_ros_driver_elf2_hikrobot"
DASHBOARD = ROOT / "05_realtime_display"
TEXT_SUFFIXES = {".sh", ".py", ".cpp", ".hpp", ".h", ".yaml", ".yml", ".launch", ".xml", ".md", ".json", ".ts", ".tsx", ".css", ".html"}
PYTHON_SKIP_PARTS = {".git", "node_modules", "dist", "build", "devel", "install", "thirdparty", "3rdparty"}
SHELL_SKIP_PARTS = {".git", "node_modules", "dist", "build", "devel", "install", "thirdparty", "3rdparty"}
PLACEHOLDER_ALLOW_PARTS = {"docs", "source_provenance"}
PLACEHOLDER_ALLOW_NAMES = {"README.md", "README_REPRODUCE.md", "verify_submission_static.py", "validate_local_configs.py"}
PLACEHOLDER_ALLOW_SUFFIXES = {".example.yaml", ".example.yml", ".example.json", ".example.md", ".sample.txt", ".sample.json"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def is_under(path: Path, parts: set[str]) -> bool:
    return any(part in parts for part in path.relative_to(ROOT).parts)


def text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if "node_modules" in path.parts or "dist" in path.parts:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
    return files


def is_allowed_placeholder_file(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    name = rel.name
    rel_posix = rel.as_posix()
    if name in PLACEHOLDER_ALLOW_NAMES:
        return True
    if any(rel_posix.endswith(suffix) for suffix in PLACEHOLDER_ALLOW_SUFFIXES):
        return True
    return any(part in PLACEHOLDER_ALLOW_PARTS for part in rel.parts)


def check_line_endings(failures: list[str]) -> None:
    crlf_files = []
    for path in text_files():
        data = path.read_bytes()
        if b"\r\n" in data or data.endswith(b"\r"):
            crlf_files.append(path.relative_to(ROOT).as_posix())
    require(not crlf_files, "Text files must use LF line endings; CRLF files: " + ", ".join(crlf_files[:20]), failures)


def check_no_python_cache(failures: list[str]) -> None:
    caches = [path.relative_to(ROOT).as_posix() for path in ROOT.rglob("__pycache__") if path.is_dir() and ".git" not in path.parts]
    pycs = [path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*.pyc") if ".git" not in path.parts]
    require(not caches and not pycs, "Submission must not contain __pycache__ or .pyc files", failures)


def check_shell_syntax(failures: list[str]) -> None:
    bash = shutil.which("bash")
    require(bool(bash), "bash must be available to validate shell scripts", failures)
    if not bash:
        return
    for path in ROOT.rglob("*.sh"):
        if not path.is_file() or is_under(path, SHELL_SKIP_PARTS):
            continue
        result = subprocess.run([bash, "-n", path.relative_to(ROOT).as_posix()], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        require(result.returncode == 0, f"Shell syntax failed for {path.relative_to(ROOT).as_posix()}: {result.stderr.strip()}", failures)


def check_python_syntax(failures: list[str]) -> None:
    for path in ROOT.rglob("*.py"):
        if not path.is_file() or is_under(path, PYTHON_SKIP_PARTS):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            compile(source, path.relative_to(ROOT).as_posix(), "exec")
        except SyntaxError as exc:
            failures.append(f"Python syntax failed for {path.relative_to(ROOT).as_posix()}: {exc}")


def check_runtime_placeholders(failures: list[str]) -> None:
    placeholder_patterns = [
        re.compile(r"YOUR_"),
        re.compile(r"192\.168\.x\.x"),
        re.compile(r"100000000000000"),
    ]
    offenders = []
    for path in text_files():
        if is_allowed_placeholder_file(path):
            continue
        text = read(path)
        if any(pattern.search(text) for pattern in placeholder_patterns):
            offenders.append(path.relative_to(ROOT).as_posix())
    require(not offenders, "Runtime files must not contain placeholder hardware values outside .example/docs files: " + ", ".join(offenders[:20]), failures)


def main() -> int:
    failures: list[str] = []

    check_line_endings(failures)
    check_no_python_cache(failures)
    check_shell_syntax(failures)
    check_python_syntax(failures)
    check_runtime_placeholders(failures)

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
    require("advertiseCamera(" not in hik_src, "Hikrobot driver must publish CameraInfo on CameraInfoTopicName, not the implicit image/camera_info namespace", failures)
    require("advertise<sensor_msgs::CameraInfo>" in hik_src and "camera_info_pub.publish" in hik_src, "Hikrobot driver must explicitly advertise and publish CameraInfoTopicName", failures)
    require("ros::Rate loop_rate(publish_rate_hz)" in hik_src, "Hikrobot publish loop must use the FrameRate parameter", failures)
    require("nRet = MV_OK;\n        if (MV_OK == nRet)" not in hik_header, "Hikrobot trigger setup must not contain a fake TriggerMode success block", failures)
    require("PixelFormat" in hik_header and "MV_CC_SetEnumValue(handle, \"PixelFormat\", pixel_format_value)" in hik_header, "Hikrobot driver must map the PixelFormat parameter into the SDK setting", failures)
    require("sensor_msgs::image_encodings::RGB8" in hik_src, "Hikrobot image topic must publish RGB8 when topic name is /rgb", failures)
    require("<license>GPL-2.0-only</license>" in read(FAST_LIVO / "package.xml"), "FAST-LIVO2 package.xml license must match the GPL-2.0 upstream LICENSE", failures)
    require("<license>MIT</license>" in read(HIK / "package.xml"), "Hikrobot driver package.xml must not contain TODO license", failures)

    probe = read(DASHBOARD / "tools" / "rk3588_display_probe.py")
    require("RejectPolicy" in probe, "SSH probe must not auto-trust unknown host keys by default", failures)
    require("validate_container_name" in probe, "SSH probe must validate docker container names", failures)
    require("RK3588_ROS_CONTAINER" in probe and "rk3588_dev" in probe, "Display probe must use the unified RK3588_ROS_CONTAINER default", failures)
    require("mid360_ros" not in probe, "Display probe must not default to the old mid360_ros container", failures)
    require("address:=127.0.0.1" in probe or "bridge_address" in probe, "Foxglove bridge must not bind 0.0.0.0 by default", failures)

    require((DASHBOARD / "tools" / "rk3588_edge_status_server.py").exists(), "Realtime display must include a real edge status backend", failures)
    require((DASHBOARD / "tools" / "tests" / "test_rk3588_edge_status_server.py").exists(), "Realtime status backend must include unit tests for path parsing and command safety", failures)
    require((DASHBOARD / "web_dashboard" / "src" / "data" / "liveAdapter.ts").exists(), "Web dashboard must include a live adapter", failures)
    require((ROOT / "00_project_configuration" / "create_catkin_workspace_from_submission.sh").exists(), "Submission must include a script that assembles the catkin workspace from the packaged source trees", failures)
    require((ROOT / "00_project_configuration" / "validate_local_configs.py").exists(), "Submission must include local hardware config validation before sensor launch", failures)
    require((ROOT / ".gitattributes").exists(), "Repository must include .gitattributes with LF rules for scripts and source files", failures)
    require((ROOT / "README_REPRODUCE.md").exists(), "Submission must include README_REPRODUCE.md for end-to-end reproduction", failures)

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
