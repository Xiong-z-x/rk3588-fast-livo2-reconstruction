#!/usr/bin/env python3
"""Inspect recent raw bag files and print durations/topic counts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import rosbag


def _bag_files(root: Path) -> List[Path]:
    return sorted(
        [*root.rglob("*.bag"), *root.rglob("*.bag.active")],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _topic_counts(bag: rosbag.Bag) -> dict[str, int]:
    info = bag.get_type_and_topic_info()
    return {name: topic_info.message_count for name, topic_info in info.topics.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/root/mid360_data/raw_full_bags", type=Path)
    parser.add_argument("--limit", default=12, type=int)
    args = parser.parse_args()

    latest_file = args.root / "LATEST_RAW_FULL_RUN_DIR"
    latest = latest_file.read_text().strip() if latest_file.exists() else ""
    print(f"LATEST_RUN_DIR={latest}")

    for index, path in enumerate(_bag_files(args.root)[: args.limit], start=1):
        stat = path.stat()
        print("---")
        print(f"index={index}")
        print(f"path={path}")
        print(f"size_bytes={stat.st_size}")
        print(f"mtime_epoch={stat.st_mtime:.3f}")
        try:
            with rosbag.Bag(str(path), "r") as bag:
                start = bag.get_start_time()
                end = bag.get_end_time()
                counts = _topic_counts(bag)
                print(f"start={start:.9f}")
                print(f"end={end:.9f}")
                print(f"duration={end - start:.6f}")
                print(f"messages_total={sum(counts.values())}")
                for topic in (
                    "/livox/lidar",
                    "/livox/imu",
                    "/hikrobot_camera/rgb",
                    "/hikrobot_camera/camera_info",
                ):
                    print(f"{topic}={counts.get(topic, 0)}")
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            print(f"error={type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
