#!/usr/bin/env python3
import argparse
import json
import math
import os
import struct
from typing import Dict, Iterable

import rosbag


def _update_bbox(bbox: Dict[str, float], x: float, y: float, z: float) -> None:
    if x < bbox["min_x"]:
        bbox["min_x"] = x
    if y < bbox["min_y"]:
        bbox["min_y"] = y
    if z < bbox["min_z"]:
        bbox["min_z"] = z
    if x > bbox["max_x"]:
        bbox["max_x"] = x
    if y > bbox["max_y"]:
        bbox["max_y"] = y
    if z > bbox["max_z"]:
        bbox["max_z"] = z


def export_livox_raw_accumulated(bag_path: str, topic: str, out_bin: str, out_json: str) -> None:
    os.makedirs(os.path.dirname(out_bin), exist_ok=True)
    pack = struct.Struct("<ffff").pack
    bbox = {
        "min_x": float("inf"),
        "min_y": float("inf"),
        "min_z": float("inf"),
        "max_x": float("-inf"),
        "max_y": float("-inf"),
        "max_z": float("-inf"),
    }
    frame_count = 0
    point_count = 0
    valid_count = 0
    first_stamp = None
    last_stamp = None
    per_frame_min = None
    per_frame_max = None

    with rosbag.Bag(bag_path, "r") as bag, open(out_bin, "wb", buffering=1024 * 1024 * 16) as out:
        for _, msg, _ in bag.read_messages(topics=[topic]):
            frame_count += 1
            frame_points = int(getattr(msg, "point_num", len(msg.points)))
            if per_frame_min is None or frame_points < per_frame_min:
                per_frame_min = frame_points
            if per_frame_max is None or frame_points > per_frame_max:
                per_frame_max = frame_points
            stamp = msg.header.stamp.to_sec()
            if first_stamp is None:
                first_stamp = stamp
            last_stamp = stamp
            for point in msg.points:
                x = float(point.x)
                y = float(point.y)
                z = float(point.z)
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                    continue
                intensity = float(point.reflectivity)
                out.write(pack(x, y, z, intensity))
                _update_bbox(bbox, x, y, z)
                valid_count += 1
            point_count += frame_points
            if frame_count % 50 == 0:
                print(
                    f"[EXPORT] frames={frame_count} raw_points={point_count} valid_points={valid_count}",
                    flush=True,
                )

    summary = {
        "bag": bag_path,
        "topic": topic,
        "output_bin": out_bin,
        "frame_count": frame_count,
        "declared_point_count": point_count,
        "valid_point_count": valid_count,
        "binary_format": "little-endian float32 x,y,z,intensity",
        "point_step_bytes": 16,
        "file_size_bytes": os.path.getsize(out_bin),
        "first_stamp": first_stamp,
        "last_stamp": last_stamp,
        "duration_from_header_sec": None if first_stamp is None or last_stamp is None else last_stamp - first_stamp,
        "per_frame_point_min": per_frame_min,
        "per_frame_point_max": per_frame_max,
        "bbox_xyz": [
            bbox["min_x"],
            bbox["min_y"],
            bbox["min_z"],
            bbox["max_x"],
            bbox["max_y"],
            bbox["max_z"],
        ],
    }
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(json.dumps(summary, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True)
    parser.add_argument("--topic", default="/livox/lidar")
    parser.add_argument("--out-bin", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()
    export_livox_raw_accumulated(args.bag, args.topic, args.out_bin, args.out_json)


if __name__ == "__main__":
    main()
