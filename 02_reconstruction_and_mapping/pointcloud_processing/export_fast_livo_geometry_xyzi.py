#!/usr/bin/env python3
import argparse
import json
import math
import os
import struct

import rosbag
import sensor_msgs.point_cloud2 as pc2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True)
    parser.add_argument("--topic", default="/cloud_registered")
    parser.add_argument("--out-bin", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out_bin), exist_ok=True)
    pack = struct.Struct("<ffff").pack
    frame_count = 0
    valid_points = 0
    declared_points = 0
    bbox = [float("inf"), float("inf"), float("inf"), float("-inf"), float("-inf"), float("-inf")]
    frame_valid = []
    fields = None

    with rosbag.Bag(args.bag, "r") as bag, open(args.out_bin, "wb", buffering=16 * 1024 * 1024) as out:
        for _, msg, _ in bag.read_messages(topics=[args.topic]):
            frame_count += 1
            declared_points += msg.width * msg.height
            fields = [field.name for field in msg.fields]
            current = 0
            for x, y, z in pc2.read_points(msg, field_names=("x", "y", "z"), skip_nans=False):
                x = float(x)
                y = float(y)
                z = float(z)
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                    continue
                out.write(pack(x, y, z, 100.0))
                bbox[0] = min(bbox[0], x)
                bbox[1] = min(bbox[1], y)
                bbox[2] = min(bbox[2], z)
                bbox[3] = max(bbox[3], x)
                bbox[4] = max(bbox[4], y)
                bbox[5] = max(bbox[5], z)
                valid_points += 1
                current += 1
            frame_valid.append(current)
            if frame_count % 50 == 0:
                print(f"[EXPORT] frames={frame_count} valid_geometry_points={valid_points}", flush=True)

    summary = {
        "bag": args.bag,
        "topic": args.topic,
        "fields": fields,
        "frame_count": frame_count,
        "declared_points": declared_points,
        "valid_geometry_points": valid_points,
        "point_step_bytes": 16,
        "binary_format": "little-endian float32 x,y,z,intensity",
        "output_bin": args.out_bin,
        "file_size_bytes": os.path.getsize(args.out_bin),
        "per_frame_valid_geometry": {
            "count": len(frame_valid),
            "min": min(frame_valid) if frame_valid else None,
            "max": max(frame_valid) if frame_valid else None,
            "mean": sum(frame_valid) / len(frame_valid) if frame_valid else None,
        },
        "bbox_xyz": None if valid_points == 0 else bbox,
    }
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
