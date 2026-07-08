#!/usr/bin/env python3
"""Read-only edge status backend for the RK3588/ELF2 dashboard."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


TARGET_TOPICS = (
    "/livox/lidar",
    "/livox/imu",
    "/hikrobot_camera/rgb",
    "/hikrobot_camera/camera_info",
    "/cloud_registered",
    "/path",
    "/tf",
)

SAFE_CONTAINER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(args: list[str], timeout_s: float = 3.0) -> CommandResult:
    try:
        result = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
        return CommandResult(result.returncode, result.stdout.strip(), result.stderr.strip())
    except FileNotFoundError as exc:
        return CommandResult(127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(124, stdout.strip(), stderr.strip() or "timeout")


def validate_container(container: str) -> str:
    if not SAFE_CONTAINER_RE.fullmatch(container):
        raise argparse.ArgumentTypeError("container must match [A-Za-z0-9_.-]+")
    return container


def docker_bash(container: str, command: str, timeout_s: float = 4.0) -> CommandResult:
    return run_command(["docker", "exec", container, "bash", "-lc", command], timeout_s=timeout_s)


def ros_command(container: str, command: str, timeout_s: float = 4.0) -> CommandResult:
    setup = (
        "source /opt/ros/noetic/setup.bash; "
        "source /root/fast_lio2_ws/devel/setup.bash 2>/dev/null || true; "
        "source /root/mid360_ws/devel/setup.bash 2>/dev/null || true; "
    )
    return docker_bash(container, setup + command, timeout_s=timeout_s)


def read_mem_percent() -> tuple[str, str]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw_value = line.split(":", 1)
            number = int(raw_value.strip().split()[0])
            values[key] = number
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        if total <= 0:
            return "unknown", "warning"
        used_percent = (total - available) * 100.0 / total
        status = "ready" if used_percent < 85 else "warning"
        return f"{used_percent:.1f}", status
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}", "warning"


def read_loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text(encoding="utf-8").split()[0]
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}"


def read_rknpu_load() -> tuple[str, str]:
    candidates = (
        Path("/sys/kernel/debug/rknpu/load"),
        Path("/sys/kernel/debug/rknpu/summary"),
        Path("/sys/class/devfreq/fdab0000.npu/load"),
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
            if not raw:
                continue
            percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", raw)
            if percent_match:
                value = float(percent_match.group(1))
                return f"{value:.1f}", "ready" if value < 90 else "warning"
            return raw[:96], "ready"
        except PermissionError:
            return f"permission denied: {path}", "warning"
        except Exception as exc:  # noqa: BLE001
            return f"{path}: {exc}", "warning"
    return "not exposed", "waiting"


def parse_topic_info(text: str) -> tuple[int | None, int | None]:
    publishers: int | None = None
    subscribers: int | None = None
    current: str | None = None
    counts = {"publishers": 0, "subscribers": 0}

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Publishers:"):
            current = "publishers"
            if "None" in stripped:
                publishers = 0
            continue
        if stripped.startswith("Subscribers:"):
            current = "subscribers"
            if "None" in stripped:
                subscribers = 0
            continue
        if current and stripped.startswith("*"):
            counts[current] += 1

    if publishers is None:
        publishers = counts["publishers"]
    if subscribers is None:
        subscribers = counts["subscribers"]
    return publishers, subscribers


def read_topic_status(container: str, topic: str, measure_hz: bool, hz_window: float) -> dict[str, Any]:
    type_result = ros_command(container, f"timeout 3s rostopic type {topic}", timeout_s=4)
    if type_result.returncode != 0:
        return {
            "name": topic,
            "type": "",
            "hz": None,
            "publishers": None,
            "subscribers": None,
            "status": "offline",
            "message": type_result.stderr or type_result.stdout or "topic unavailable",
        }

    info_result = ros_command(container, f"timeout 3s rostopic info {topic}", timeout_s=4)
    publishers, subscribers = parse_topic_info(info_result.stdout) if info_result.returncode == 0 else (None, None)

    hz: float | None = None
    if measure_hz:
        hz_result = ros_command(container, f"timeout {int(hz_window + 2)}s rostopic hz -w {hz_window:g} {topic}", timeout_s=hz_window + 3)
        match = re.search(r"average rate:\s*([0-9.]+)", hz_result.stdout)
        if match:
            hz = float(match.group(1))

    return {
        "name": topic,
        "type": type_result.stdout.strip(),
        "hz": hz,
        "publishers": publishers,
        "subscribers": subscribers,
        "status": "ready" if (publishers or 0) > 0 else "waiting",
        "message": info_result.stderr if info_result.returncode != 0 else "",
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    hostname = socket.gethostname()
    mem_value, mem_status = read_mem_percent()
    rknpu_value, rknpu_status = read_rknpu_load()
    docker_result = run_command(["docker", "inspect", "--format", "{{.State.Running}}", args.container], timeout_s=3)
    docker_ready = docker_result.returncode == 0 and docker_result.stdout.strip() == "true"
    ros_list_result = ros_command(args.container, "timeout 3s rostopic list", timeout_s=4) if docker_ready else CommandResult(1, "", "container is not running")
    ros_ready = ros_list_result.returncode == 0

    topics = [read_topic_status(args.container, topic, args.measure_hz, args.hz_window) for topic in TARGET_TOPICS] if ros_ready else [
        {
            "name": topic,
            "type": "",
            "hz": None,
            "publishers": None,
            "subscribers": None,
            "status": "offline",
            "message": ros_list_result.stderr or "ROS Master unavailable",
        }
        for topic in TARGET_TOPICS
    ]

    metrics = [
        {"label": "CPU 负载", "value": read_loadavg(), "unit": "loadavg 1min", "status": "ready"},
        {"label": "内存占用", "value": mem_value, "unit": "%", "status": mem_status},
        {"label": "RKNPU 负载", "value": rknpu_value, "unit": "% / raw", "status": rknpu_status},
        {"label": "ROS Master", "value": "online" if ros_ready else "offline", "unit": "11311", "status": "ready" if ros_ready else "offline"},
    ]

    events = [
        {"time": now, "level": "INFO", "text": f"status backend sampled host={hostname} container={args.container}"},
        {"time": now, "level": "INFO" if docker_ready else "WARN", "text": f"docker container running={docker_ready}"},
        {"time": now, "level": "INFO" if ros_ready else "WARN", "text": ros_list_result.stderr or "ROS topic list reachable"},
    ]

    return {
        "adapterState": "live" if ros_ready else "error",
        "sourceLabel": "RK3588/ELF2 edge status backend",
        "bridgeUrl": f"ws://{args.bridge_host}:{args.bridge_port}",
        "primaryTopic": "/cloud_registered",
        "timestamp": now,
        "note": "Values are sampled from Linux procfs/sysfs, Docker and ROS1 command-line tools on the edge device.",
        "host": hostname,
        "container": args.container,
        "metrics": metrics,
        "topics": topics,
        "pose": {"source": "live ROS pose parsing not enabled in this lightweight backend"},
        "events": events,
    }


class StatusHandler(BaseHTTPRequestHandler):
    server_version = "RK3588EdgeStatus/1.0"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/api/status", "/status"}:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(b"not found")
            return

        payload = build_snapshot(self.server.args)  # type: ignore[attr-defined]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        print(f"[{time.strftime('%F %T')}] {self.address_string()} {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve real read-only RK3588/ELF2 runtime status for the web dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8766, type=int)
    parser.add_argument("--container", default=os.environ.get("RK3588_ROS_CONTAINER", "rk3588_dev"), type=validate_container)
    parser.add_argument("--bridge-host", default="127.0.0.1")
    parser.add_argument("--bridge-port", default=8765, type=int)
    parser.add_argument("--measure-hz", action="store_true", help="Also run rostopic hz; useful but slower.")
    parser.add_argument("--hz-window", default=2.0, type=float)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), StatusHandler)
    server.args = args  # type: ignore[attr-defined]
    print(f"Serving edge status on http://{args.host}:{args.port}/api/status")
    print("Default binding is loopback. Use --host 0.0.0.0 only on a trusted lab network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
