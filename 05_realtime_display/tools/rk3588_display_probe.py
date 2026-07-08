#!/usr/bin/env python3
"""
Read-only RK3588 display readiness probe.

Default mode only checks SSH, Docker, ROS, topics, foxglove_bridge and ports.
It does not start, stop, restart, install, or modify anything.

Use --start-bridge only after explicit approval, and only when /livox/lidar is
already visible through rostopic.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shlex
import sys
from dataclasses import dataclass

import paramiko


TARGET_TOPICS = (
    "/livox/lidar",
    "/livox/imu",
    "/cloud_registered",
    "/Odometry",
    "/path",
    "/tf",
    "/tf_static",
)

SAFE_CONTAINER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_container_name(container: str) -> str:
    if not SAFE_CONTAINER_RE.fullmatch(container):
        raise argparse.ArgumentTypeError("container name must match [A-Za-z0-9_.-]+")
    return container


def validate_bridge_address(address: str) -> str:
    if not re.fullmatch(r"[0-9A-Za-z_.:-]+", address):
        raise argparse.ArgumentTypeError("bridge address contains unsupported characters")
    return address


@dataclass(frozen=True)
class RemoteResult:
    label: str
    command: str
    returncode: int
    stdout: str
    stderr: str


def run_remote(client: paramiko.SSHClient, label: str, command: str, timeout_s: int = 40) -> RemoteResult:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout_s)
    del stdin
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    rc = stdout.channel.recv_exit_status()
    return RemoteResult(label=label, command=command, returncode=rc, stdout=out, stderr=err)


def print_result(result: RemoteResult) -> None:
    print(f"\n===== {result.label} =====")
    print(f"RC={result.returncode}")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)


def build_container_probe(container: str) -> str:
    topics = " ".join(TARGET_TOPICS)
    container_q = shlex.quote(container)
    return f"""
docker exec {container_q} bash -lc '
echo "===== identity ====="
hostname; whoami; pwd

echo "===== ros_setup ====="
if [ -f /opt/ros/noetic/setup.bash ]; then source /opt/ros/noetic/setup.bash; echo sourced_opt; fi
if [ -f /root/mid360_ws/devel/setup.bash ]; then source /root/mid360_ws/devel/setup.bash; echo sourced_ws; fi
command -v rostopic || true
command -v rosnode || true
command -v roslaunch || true
env | grep -E "^(ROS|CATKIN|CMAKE_PREFIX_PATH|HOSTNAME)=" | sort || true

echo "===== processes ====="
ps -ef | grep -E "roscore|rosmaster|roslaunch|livox|fast_lio|lio|foxglove" | grep -v grep || true

echo "===== ports ====="
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null || true) | grep -E ":11311|:8765|State|LISTEN" | sed -n "1,120p"

echo "===== rostopic_list ====="
timeout 6s rostopic list 2>&1 | sort

echo "===== rosnode_list ====="
timeout 6s rosnode list 2>&1 | sort

echo "===== target_topic_info ====="
for t in {topics}; do
  echo "--- $t ---"
  timeout 5s rostopic info "$t" 2>&1 | sed -n "1,80p"
done

echo "===== livox_lidar_hz_short ====="
timeout 8s rostopic hz /livox/lidar 2>&1 | sed -n "1,80p"

echo "===== foxglove_bridge ====="
(rospack find foxglove_bridge && echo FOXGLOVE_PACKAGE_FOUND) 2>&1 || true
(dpkg -l 2>/dev/null | grep -i foxglove || true)
'
""".strip()


def build_bridge_start(container: str, bridge_address: str) -> str:
    container_q = shlex.quote(container)
    bridge_address_q = shlex.quote(bridge_address)
    return f"""
docker exec -d {container_q} bash -lc '
source /opt/ros/noetic/setup.bash
source /root/mid360_ws/devel/setup.bash 2>/dev/null || true
exec roslaunch foxglove_bridge foxglove_bridge.launch port:=8765 address:={bridge_address_q}
'
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe RK3588 ROS/Foxglove display readiness.")
    parser.add_argument("--host", default="192.168.x.x")
    parser.add_argument("--user", default="cat")
    parser.add_argument("--container", default="mid360_ros", type=validate_container_name)
    parser.add_argument("--bridge-address", default="127.0.0.1", type=validate_bridge_address)
    parser.add_argument("--password-env", default="RK3588_PASS")
    parser.add_argument("--start-bridge", action="store_true", help="Start foxglove_bridge. Requires explicit user approval.")
    args = parser.parse_args()

    password = os.environ.get(args.password_env)
    if not password:
        password = getpass.getpass(f"SSH password for {args.user}@{args.host}: ")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=args.host,
            username=args.user,
            password=password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )

        checks = [
            (
                "host_identity",
                "hostname; whoami; uname -a",
                20,
            ),
            (
                "docker_ps",
                "docker ps --format 'table {{.ID}}\\t{{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'",
                20,
            ),
            (
                "docker_network",
                "for id in $(docker ps -q); do docker inspect --format '{{.Name}} network={{.HostConfig.NetworkMode}} ports={{json .NetworkSettings.Ports}}' $id; done",
                20,
            ),
            (
                "container_ros_probe",
                build_container_probe(args.container),
                80,
            ),
        ]

        for label, command, timeout_s in checks:
            print_result(run_remote(client, label, command, timeout_s))

        if args.start_bridge:
            print("\n===== start_bridge_requested =====")
            print(f"Starting foxglove_bridge on {args.bridge_address}:8765. This assumes ROS Master and /livox/lidar are already available.")
            print_result(run_remote(client, "start_bridge", build_bridge_start(args.container, args.bridge_address), 20))
            print_result(
                run_remote(
                    client,
                    "port_8765_after_start",
                    f"docker exec {shlex.quote(args.container)} bash -lc '(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null || true) | grep -E \":8765|State|LISTEN\" | sed -n \"1,80p\"'",
                    20,
                )
            )
        else:
            print("\n===== bridge_not_started =====")
            print("Default mode is read-only. Re-run with --start-bridge only after ROS Master and /livox/lidar are confirmed.")
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
