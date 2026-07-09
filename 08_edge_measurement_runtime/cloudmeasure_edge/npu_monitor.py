from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import BoardConfig


@dataclass(frozen=True)
class NpuLoad:
    core0: int
    core1: int
    core2: int
    average: float
    raw: str


def parse_rknpu_load(text: str) -> NpuLoad:
    match = re.search(
        r"Core0:\s*(\d+)%\s*,\s*Core1:\s*(\d+)%\s*,\s*Core2:\s*(\d+)%",
        text,
    )
    if not match:
        raise ValueError(f"Unable to parse RK3588 NPU load output: {text!r}")
    values = tuple(int(match.group(index)) for index in range(1, 4))
    return NpuLoad(
        core0=values[0],
        core1=values[1],
        core2=values[2],
        average=round(sum(values) / 3, 1),
        raw=text.strip(),
    )


def read_npu_load_local(path: str = "/sys/kernel/debug/rknpu/load") -> NpuLoad:
    return parse_rknpu_load(Path(path).read_text(encoding="utf-8", errors="replace"))


def read_npu_load_over_ssh(config: BoardConfig, timeout: int = 8) -> NpuLoad:
    user_host = f"{config.user}@{config.host}"
    cat_command = f"cat {shlex.quote(config.npu_load_path)}"
    remote = f"sudo {cat_command}" if config.use_sudo_for_npu_load else cat_command
    strict_value = "yes" if config.strict_host_key_checking else "accept-new"
    command = [
        "ssh",
        "-o",
        f"StrictHostKeyChecking={strict_value}",
        "-o",
        f"UserKnownHostsFile={Path(config.known_hosts_path).expanduser()}",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
    ]
    if config.ssh_key_path:
        command.extend(["-i", config.ssh_key_path])
    command.extend([user_host, remote])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 3, check=False)
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    if completed.returncode != 0:
        raise RuntimeError(f"SSH NPU load command failed: {output}")
    return parse_rknpu_load(output)


def read_npu_load(config: BoardConfig, timeout: int = 8) -> NpuLoad:
    if config.host in {"", "localhost", "127.0.0.1", "::1"}:
        return read_npu_load_local(config.npu_load_path)
    return read_npu_load_over_ssh(config, timeout=timeout)
