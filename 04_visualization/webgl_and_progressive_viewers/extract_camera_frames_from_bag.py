#!/usr/bin/env python3
"""Extract evenly spaced camera frames from a ROS1 bag without cv_bridge."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
from PIL import Image
import rosbag


def _image_to_array(msg: object) -> np.ndarray:
    height = int(msg.height)
    width = int(msg.width)
    encoding = str(msg.encoding).lower()
    data = np.frombuffer(msg.data, dtype=np.uint8)

    if encoding in ("rgb8", "bgr8"):
        expected = height * width * 3
        if data.size < expected:
            raise ValueError(f"short image buffer: {data.size} < {expected}")
        arr = data[:expected].reshape((height, width, 3))
        if encoding == "bgr8":
            arr = arr[:, :, ::-1]
        return arr.copy()

    if encoding in ("mono8", "8uc1"):
        expected = height * width
        if data.size < expected:
            raise ValueError(f"short image buffer: {data.size} < {expected}")
        mono = data[:expected].reshape((height, width))
        return np.repeat(mono[:, :, None], 3, axis=2)

    raise ValueError(f"unsupported encoding: {msg.encoding}")


def _read_messages(bag_path: Path, topic: str) -> List[Tuple[int, object, object]]:
    frames: List[Tuple[int, object, object]] = []
    with rosbag.Bag(str(bag_path), "r") as bag:
        for index, (_, msg, stamp) in enumerate(bag.read_messages(topics=[topic])):
            frames.append((index, msg, stamp))
    return frames


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, type=Path)
    parser.add_argument("--topic", default="/hikrobot_camera/rgb")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--count", default=6, type=int)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frames = _read_messages(args.bag, args.topic)
    if not frames:
        raise RuntimeError(f"no frames found on {args.topic} in {args.bag}")

    indices = np.linspace(0, len(frames) - 1, min(args.count, len(frames))).round().astype(int)
    records: List[str] = []
    for out_index, frame_index in enumerate(indices):
        original_index, msg, bag_stamp = frames[int(frame_index)]
        arr = _image_to_array(msg)
        out_path = args.out_dir / f"frame_{out_index}_idx{original_index}.png"
        Image.fromarray(arr).save(out_path)
        header_stamp = getattr(msg, "header", None).stamp.to_sec() if getattr(msg, "header", None) else 0.0
        records.append(
            f"{out_path.name} original_index={original_index} "
            f"bag_stamp={bag_stamp.to_sec():.9f} header_stamp={header_stamp:.9f} "
            f"encoding={msg.encoding} size={msg.width}x{msg.height}"
        )

    (args.out_dir / "camera_frames.txt").write_text("\n".join(records) + "\n", encoding="utf-8")
    print(f"frames_total={len(frames)}")
    print(f"frames_written={len(indices)}")
    print(f"out_dir={args.out_dir}")


if __name__ == "__main__":
    main()
