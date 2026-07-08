#!/usr/bin/env python3
import argparse
import json
import math
import os
import struct
from typing import Dict, Iterable, List, Sequence, Tuple

import rosbag
import sensor_msgs.point_cloud2 as pc2


PointRGB = Tuple[float, float, float, int, int, int, float]


def _rgb_to_uint(rgb_value: object) -> int:
    if isinstance(rgb_value, float):
        return struct.unpack("<I", struct.pack("<f", rgb_value))[0] & 0x00FFFFFF
    return int(rgb_value) & 0x00FFFFFF


def _rgb_to_float(r: int, g: int, b: int) -> float:
    packed = (int(r) << 16) | (int(g) << 8) | int(b)
    return struct.unpack("<f", struct.pack("<I", packed))[0]


def _rgb_channels(rgb_value: object) -> Tuple[int, int, int]:
    packed = _rgb_to_uint(rgb_value)
    return (packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF


def _update_bbox(bbox: Dict[str, float], x: float, y: float, z: float) -> None:
    bbox["min_x"] = min(bbox["min_x"], x)
    bbox["min_y"] = min(bbox["min_y"], y)
    bbox["min_z"] = min(bbox["min_z"], z)
    bbox["max_x"] = max(bbox["max_x"], x)
    bbox["max_y"] = max(bbox["max_y"], y)
    bbox["max_z"] = max(bbox["max_z"], z)


def _empty_bbox() -> Dict[str, float]:
    return {
        "min_x": float("inf"),
        "min_y": float("inf"),
        "min_z": float("inf"),
        "max_x": float("-inf"),
        "max_y": float("-inf"),
        "max_z": float("-inf"),
    }


def _read_cloud_points(msg) -> List[PointRGB]:
    names = [field.name for field in msg.fields]
    if "rgb" in names:
        fields = ("x", "y", "z", "rgb")
        out = []
        for x, y, z, rgb in pc2.read_points(msg, field_names=fields, skip_nans=True):
            x = float(x); y = float(y); z = float(z)
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                continue
            r, g, b = _rgb_channels(rgb)
            out.append((x, y, z, r, g, b, _rgb_to_float(r, g, b)))
        return out
    if all(name in names for name in ("r", "g", "b")):
        fields = ("x", "y", "z", "r", "g", "b")
        out = []
        for x, y, z, r, g, b in pc2.read_points(msg, field_names=fields, skip_nans=True):
            x = float(x); y = float(y); z = float(z)
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                continue
            ri, gi, bi = int(r), int(g), int(b)
            out.append((x, y, z, ri, gi, bi, _rgb_to_float(ri, gi, bi)))
        return out
    fields = ("x", "y", "z")
    out = []
    for x, y, z in pc2.read_points(msg, field_names=fields, skip_nans=True):
        x = float(x); y = float(y); z = float(z)
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue
        out.append((x, y, z, 255, 255, 255, _rgb_to_float(255, 255, 255)))
    return out


def _write_ply(path: str, points: Sequence[PointRGB]) -> None:
    with open(path, "w", encoding="ascii") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        for x, y, z, r, g, b, _ in points:
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {r:d} {g:d} {b:d}\n")


def _write_pcd(path: str, points: Sequence[PointRGB]) -> None:
    with open(path, "w", encoding="ascii") as f:
        f.write("# .PCD v0.7 - Point Cloud Data file format\n")
        f.write("VERSION 0.7\n")
        f.write("FIELDS x y z rgb\n")
        f.write("SIZE 4 4 4 4\n")
        f.write("TYPE F F F F\n")
        f.write("COUNT 1 1 1 1\n")
        f.write(f"WIDTH {len(points)}\n")
        f.write("HEIGHT 1\n")
        f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
        f.write(f"POINTS {len(points)}\n")
        f.write("DATA ascii\n")
        for x, y, z, _, _, _, rgb_float in points:
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {rgb_float:.8e}\n")


def _summarise_points(points: Sequence[PointRGB]) -> Dict[str, object]:
    bbox = _empty_bbox()
    colors = set()
    for x, y, z, r, g, b, _ in points:
        _update_bbox(bbox, x, y, z)
        colors.add((r, g, b))
    bbox_values = None
    if points:
        bbox_values = [
            bbox["min_x"],
            bbox["min_y"],
            bbox["min_z"],
            bbox["max_x"],
            bbox["max_y"],
            bbox["max_z"],
        ]
    return {
        "points": len(points),
        "bbox_xyz": bbox_values,
        "unique_rgb_colors": len(colors),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True)
    parser.add_argument("--topic", default="/cloud_registered")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--prefix", default="cloud_registered")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    accumulated: List[PointRGB] = []
    last: List[PointRGB] = []
    frame_counts: List[int] = []
    fields = None
    frame_count = 0

    with rosbag.Bag(args.bag, "r") as bag:
        for _, msg, _ in bag.read_messages(topics=[args.topic]):
            frame_count += 1
            fields = [field.name for field in msg.fields]
            points = _read_cloud_points(msg)
            frame_counts.append(len(points))
            last = points
            accumulated.extend(points)
            if frame_count % 50 == 0:
                print(
                    f"[EXPORT] frames={frame_count} accumulated_points={len(accumulated)}",
                    flush=True,
                )

    outputs = []
    for name, points in [
        (f"{args.prefix}_last_color", last),
        (f"{args.prefix}_accumulated_full_color_NO_VOXEL", accumulated),
    ]:
        ply = os.path.join(args.out_dir, f"{name}.ply")
        pcd = os.path.join(args.out_dir, f"{name}.pcd")
        _write_ply(ply, points)
        _write_pcd(pcd, points)
        item = {"name": name, "ply": ply, "pcd": pcd, **_summarise_points(points)}
        item["ply_size"] = os.path.getsize(ply)
        item["pcd_size"] = os.path.getsize(pcd)
        outputs.append(item)

    summary = {
        "bag": args.bag,
        "topic": args.topic,
        "fields": fields,
        "frame_count": frame_count,
        "per_frame_valid_points": {
            "count": len(frame_counts),
            "min": min(frame_counts) if frame_counts else None,
            "max": max(frame_counts) if frame_counts else None,
            "mean": sum(frame_counts) / len(frame_counts) if frame_counts else None,
        },
        "outputs": outputs,
    }
    summary_path = os.path.join(args.out_dir, f"{args.prefix}_export_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
