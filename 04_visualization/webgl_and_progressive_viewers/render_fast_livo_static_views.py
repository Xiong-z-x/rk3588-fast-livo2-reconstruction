#!/usr/bin/env python3
"""Render static views from a FAST-LIVO output rosbag.

This script is intentionally dependency-light: ROS Python, NumPy and Pillow.
It reads colored /cloud_registered PointCloud2 messages, voxel-downsamples
them, writes a PLY, and renders top/side/isometric PNG views for quick display.
"""

from __future__ import annotations

import argparse
import math
import os
import struct
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np
from PIL import Image, ImageDraw
import rosbag
from sensor_msgs import point_cloud2


VoxelKey = Tuple[int, int, int]
PointValue = Tuple[float, float, float, int, int, int]


def decode_rgb(value: object) -> Tuple[int, int, int]:
    if isinstance(value, float):
        packed = struct.pack("<f", value)
        rgb_uint = struct.unpack("<I", packed)[0]
    else:
        rgb_uint = int(value)
    red = (rgb_uint >> 16) & 255
    green = (rgb_uint >> 8) & 255
    blue = rgb_uint & 255
    return red, green, blue


def read_voxel_points(
    bag_path: Path,
    topic: str,
    voxel: float,
    max_frames: int,
    frame_stride: int,
    point_stride: int,
) -> Tuple[np.ndarray, np.ndarray, int, int]:
    voxels: Dict[VoxelKey, PointValue] = {}
    raw_points = 0
    frame_count = 0

    with rosbag.Bag(str(bag_path), "r") as bag:
        for frame_index, (_, msg, _) in enumerate(bag.read_messages(topics=[topic])):
            if frame_stride > 1 and frame_index % frame_stride != 0:
                continue
            if max_frames > 0 and frame_count >= max_frames:
                break
            frame_count += 1
            if msg.width == 0:
                continue
            fields = [field.name for field in msg.fields]
            if "rgb" in fields:
                field_names = ("x", "y", "z", "rgb")
            elif "rgba" in fields:
                field_names = ("x", "y", "z", "rgba")
            else:
                field_names = ("x", "y", "z")

            for point_index, point in enumerate(
                point_cloud2.read_points(msg, field_names=field_names, skip_nans=True)
            ):
                if point_stride > 1 and point_index % point_stride != 0:
                    continue
                raw_points += 1
                x, y, z = float(point[0]), float(point[1]), float(point[2])
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                    continue
                if len(point) >= 4:
                    red, green, blue = decode_rgb(point[3])
                else:
                    red, green, blue = 80, 160, 255
                key = (int(math.floor(x / voxel)), int(math.floor(y / voxel)), int(math.floor(z / voxel)))
                voxels[key] = (x, y, z, red, green, blue)

    if not voxels:
        raise RuntimeError(f"No valid points found in {bag_path} topic {topic}")

    arr = np.asarray(list(voxels.values()), dtype=np.float32)
    points = arr[:, :3]
    colors = np.clip(arr[:, 3:6], 0, 255).astype(np.uint8)
    return points, colors, raw_points, frame_count


def write_ply(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    with path.open("wb") as handle:
        header = (
            "ply\n"
            "format binary_little_endian 1.0\n"
            f"element vertex {len(points)}\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "property uchar red\n"
            "property uchar green\n"
            "property uchar blue\n"
            "end_header\n"
        )
        handle.write(header.encode("ascii"))
        dtype = np.dtype(
            [
                ("x", "<f4"),
                ("y", "<f4"),
                ("z", "<f4"),
                ("red", "u1"),
                ("green", "u1"),
                ("blue", "u1"),
            ]
        )
        out = np.empty(len(points), dtype=dtype)
        out["x"], out["y"], out["z"] = points[:, 0], points[:, 1], points[:, 2]
        out["red"], out["green"], out["blue"] = colors[:, 0], colors[:, 1], colors[:, 2]
        handle.write(out.tobytes())


def project_points(points: np.ndarray, mode: str) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    if mode == "top_xy":
        return np.column_stack((x, y))
    if mode == "side_xz":
        return np.column_stack((x, z))
    if mode == "iso":
        u = 0.8660254 * x - 0.8660254 * y
        v = 0.50 * x + 0.50 * y - z
        return np.column_stack((u, v))
    raise ValueError(mode)


def render_projection(
    points: np.ndarray,
    colors: np.ndarray,
    mode: str,
    title: str,
    size: Tuple[int, int],
    margin: int = 36,
) -> Image.Image:
    width, height = size
    bg = np.full((height, width, 3), 248, dtype=np.uint8)
    proj = project_points(points, mode)
    mins = proj.min(axis=0)
    maxs = proj.max(axis=0)
    span = np.maximum(maxs - mins, 1e-6)
    scale = min((width - 2 * margin) / span[0], (height - 2 * margin) / span[1])
    xy = (proj - mins) * scale
    px = np.clip((xy[:, 0] + margin).astype(np.int32), 0, width - 1)
    py = np.clip((height - 1 - (xy[:, 1] + margin)).astype(np.int32), 0, height - 1)

    if mode == "iso":
        order = np.argsort(points[:, 2])
        px, py, draw_colors = px[order], py[order], colors[order]
    else:
        draw_colors = colors

    bg[py, px] = draw_colors
    image = Image.fromarray(bg, "RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, 26], fill=(255, 255, 255))
    draw.text((10, 7), title, fill=(20, 32, 44))
    draw.rectangle([0, 0, width - 1, height - 1], outline=(180, 190, 200))
    return image


def make_overview(
    output: Path,
    points: np.ndarray,
    colors: np.ndarray,
    raw_points: int,
    frame_count: int,
    voxel: float,
    bag_path: Path,
) -> None:
    panel_size = (900, 560)
    panels = [
        render_projection(points, colors, "top_xy", "Top View: X-Y", panel_size),
        render_projection(points, colors, "side_xz", "Side View: X-Z", panel_size),
        render_projection(points, colors, "iso", "Isometric View", panel_size),
    ]
    canvas = Image.new("RGB", (1920, 1200), (242, 245, 248))
    draw = ImageDraw.Draw(canvas)
    draw.text((26, 18), "FAST-LIVO Static Reconstruction Result - Official NTU-VIRAL eee_03", fill=(12, 24, 36))
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    info = (
        f"bag={bag_path}\n"
        f"frames={frame_count} sampled_points={raw_points} voxel_points={len(points)} voxel={voxel:.3f} m\n"
        f"extent_x={mins[0]:.2f}..{maxs[0]:.2f}  "
        f"extent_y={mins[1]:.2f}..{maxs[1]:.2f}  "
        f"extent_z={mins[2]:.2f}..{maxs[2]:.2f}"
    )
    draw.multiline_text((26, 42), info, fill=(30, 42, 54), spacing=4)
    canvas.paste(panels[0], (26, 120))
    canvas.paste(panels[1], (990, 120))
    canvas.paste(panels[2], (510, 700))
    canvas.save(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, type=Path)
    parser.add_argument("--topic", default="/cloud_registered")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--voxel", default=0.08, type=float)
    parser.add_argument("--max-frames", default=0, type=int)
    parser.add_argument("--frame-stride", default=1, type=int)
    parser.add_argument("--point-stride", default=1, type=int)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    points, colors, raw_points, frame_count = read_voxel_points(
        args.bag,
        args.topic,
        args.voxel,
        args.max_frames,
        args.frame_stride,
        args.point_stride,
    )
    ply_path = args.out_dir / "official_eee03_static_colored_map_voxel.ply"
    png_path = args.out_dir / "official_eee03_static_colored_map_overview.png"
    write_ply(ply_path, points, colors)
    make_overview(png_path, points, colors, raw_points, frame_count, args.voxel, args.bag)
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    print(f"PNG={png_path}")
    print(f"PLY={ply_path}")
    print(f"frames={frame_count}")
    print(f"sampled_points={raw_points}")
    print(f"voxel_points={len(points)}")
    print(f"extent_min={mins.tolist()}")
    print(f"extent_max={maxs.tolist()}")


if __name__ == "__main__":
    main()
