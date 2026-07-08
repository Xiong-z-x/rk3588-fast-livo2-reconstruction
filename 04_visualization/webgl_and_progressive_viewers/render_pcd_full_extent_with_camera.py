#!/usr/bin/env python3
"""Render a FAST-LIVO2 final PCD with matching camera frames.

This script reads the final PCD directly. It does not voxel-filter, crop, or
resample the point cloud. Projections are full extent views intended for visual
inspection and reporting.
"""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _parse_pcd_header(path: Path) -> Tuple[Dict[str, List[str]], int]:
    metadata: Dict[str, List[str]] = {}
    offset = 0
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ValueError(f"PCD header has no DATA line: {path}")
            offset += len(line)
            text = line.decode("ascii", errors="strict").strip()
            if not text or text.startswith("#"):
                continue
            parts = text.split()
            metadata[parts[0].upper()] = parts[1:]
            if parts[0].upper() == "DATA":
                return metadata, offset


def _read_pcd_xyz_rgb(path: Path) -> Tuple[np.ndarray, np.ndarray, Dict[str, List[str]]]:
    metadata, offset = _parse_pcd_header(path)
    data_kind = metadata.get("DATA", [""])[0].lower()
    fields = metadata.get("FIELDS", [])
    sizes = [int(value) for value in metadata.get("SIZE", [])]
    types = metadata.get("TYPE", [])
    counts = [int(value) for value in metadata.get("COUNT", ["1"] * len(fields))]
    points_count = int(metadata.get("POINTS", ["0"])[0])

    if fields[:3] != ["x", "y", "z"]:
        raise ValueError(f"Expected PCD fields to start with x y z, got {fields}")
    if "rgb" not in fields and "rgba" not in fields:
        raise ValueError(f"Expected rgb or rgba field in {path}, got {fields}")
    if any(count != 1 for count in counts):
        raise ValueError(f"Only COUNT 1 fields are supported, got {counts}")

    dtype_fields = []
    for name, size, type_name in zip(fields, sizes, types):
        if type_name == "F" and size == 4:
            dtype_fields.append((name, "<f4"))
        elif type_name == "F" and size == 8:
            dtype_fields.append((name, "<f8"))
        elif type_name == "U" and size == 4:
            dtype_fields.append((name, "<u4"))
        elif type_name == "I" and size == 4:
            dtype_fields.append((name, "<i4"))
        elif type_name == "U" and size == 1:
            dtype_fields.append((name, "u1"))
        else:
            raise ValueError(f"Unsupported PCD field type: {name} {type_name}{size}")

    if data_kind == "binary":
        dtype = np.dtype(dtype_fields)
        with path.open("rb") as handle:
            handle.seek(offset)
            data = np.frombuffer(handle.read(points_count * dtype.itemsize), dtype=dtype, count=points_count)
        points = np.column_stack(
            [
                data["x"].astype(np.float32),
                data["y"].astype(np.float32),
                data["z"].astype(np.float32),
            ]
        )
        rgb_field = "rgb" if "rgb" in data.dtype.names else "rgba"
        rgb_uint = data[rgb_field].astype(np.uint32)
    elif data_kind == "ascii":
        arr = np.loadtxt(path, comments="#", skiprows=len(metadata) + 1)
        points = arr[:, :3].astype(np.float32)
        rgb_index = fields.index("rgb") if "rgb" in fields else fields.index("rgba")
        rgb_uint = arr[:, rgb_index].astype(np.uint32)
    else:
        raise ValueError(f"Unsupported PCD DATA kind: {data_kind}")

    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    rgb_uint = rgb_uint[finite]

    colors = np.column_stack(
        [
            ((rgb_uint >> 16) & 255),
            ((rgb_uint >> 8) & 255),
            (rgb_uint & 255),
        ]
    ).astype(np.uint8)
    return points, colors, metadata


def _project(points: np.ndarray, mode: str) -> Tuple[np.ndarray, np.ndarray | None]:
    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    if mode == "top_xy":
        return np.column_stack((x, y)), z
    if mode == "front_xz":
        return np.column_stack((x, z)), y
    if mode == "side_yz":
        return np.column_stack((y, z)), x
    if mode == "iso":
        u = 0.8660254 * x - 0.8660254 * y
        v = 0.35 * x + 0.35 * y - z
        return np.column_stack((u, v)), z
    raise ValueError(mode)


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_label(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font: ImageFont.ImageFont) -> None:
    draw.rectangle([xy[0] - 8, xy[1] - 5, xy[0] + 700, xy[1] + 25], fill=(255, 255, 255))
    draw.text(xy, text, fill=(20, 32, 44), font=font)


def _render_projection(
    points: np.ndarray,
    colors: np.ndarray,
    mode: str,
    title: str,
    size: Tuple[int, int],
    margin: int = 38,
) -> Image.Image:
    width, height = size
    background = np.full((height, width, 3), 250, dtype=np.uint8)
    projected, depth = _project(points, mode)
    mins = projected.min(axis=0)
    maxs = projected.max(axis=0)
    span = np.maximum(maxs - mins, 1e-9)
    scale = min((width - margin * 2) / span[0], (height - margin * 2) / span[1])
    xy = (projected - mins) * scale
    px = np.clip((xy[:, 0] + margin).astype(np.int32), 0, width - 1)
    py = np.clip((height - 1 - (xy[:, 1] + margin)).astype(np.int32), 0, height - 1)

    order = np.arange(len(points))
    if depth is not None:
        order = np.argsort(depth)
    background[py[order], px[order]] = colors[order]

    image = Image.fromarray(background)
    draw = ImageDraw.Draw(image)
    font = _load_font(18)
    _draw_label(draw, (14, 9), title, font)
    draw.rectangle([0, 0, width - 1, height - 1], outline=(182, 190, 202))
    return image


def _make_cloud_montage(
    result_dir: Path,
    points: np.ndarray,
    colors: np.ndarray,
    metadata: Dict[str, List[str]],
) -> Tuple[Path, Path]:
    renders = result_dir / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    panel_size = (930, 560)
    views = [
        ("top_xy", "Top XY - full extent"),
        ("front_xz", "Front XZ - full extent"),
        ("side_yz", "Side YZ - full extent"),
        ("iso", "Isometric - full extent"),
    ]
    panels = [_render_projection(points, colors, mode, title, panel_size) for mode, title in views]

    canvas = Image.new("RGB", (1924, 1240), (243, 246, 249))
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(25)
    body_font = _load_font(17)
    draw.text((28, 18), "FAST-LIVO2 final colored PCD - full extent / no crop / no downsample", fill=(13, 27, 42), font=title_font)
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    span = maxs - mins
    rgb_uint = (colors[:, 0].astype(np.uint32) << 16) | (colors[:, 1].astype(np.uint32) << 8) | colors[:, 2].astype(np.uint32)
    coarse_unique_colors = int(np.unique((colors // 16).reshape(-1, 3), axis=0).shape[0])
    info = (
        f"points={len(points):,}  header_points={metadata.get('POINTS', ['?'])[0]}  "
        f"nonblack={int(np.count_nonzero(rgb_uint)):,}  coarse_colors={coarse_unique_colors}\n"
        f"bbox_min=({mins[0]:.3f}, {mins[1]:.3f}, {mins[2]:.3f})  "
        f"bbox_max=({maxs[0]:.3f}, {maxs[1]:.3f}, {maxs[2]:.3f})  "
        f"span=({span[0]:.3f}, {span[1]:.3f}, {span[2]:.3f})"
    )
    draw.multiline_text((28, 54), info, fill=(39, 52, 68), font=body_font, spacing=5)

    positions = [(28, 112), (966, 112), (28, 690), (966, 690)]
    for panel, pos in zip(panels, positions):
        canvas.paste(panel, pos)

    montage_path = renders / "all_raw_full_extent_no_crop_montage.png"
    canvas.save(montage_path)

    stats_path = renders / "all_raw_stats.txt"
    stats_path.write_text(
        "\n".join(
            [
                f"points={len(points)}",
                f"header_points={metadata.get('POINTS', ['?'])[0]}",
                f"bbox_min={mins.tolist()}",
                f"bbox_max={maxs.tolist()}",
                f"bbox_span={span.tolist()}",
                f"nonblack_rgb_points={int(np.count_nonzero(rgb_uint))}",
                f"coarse_unique_colors={coarse_unique_colors}",
                "render_points_after_outlier_crop=not_applicable_no_crop",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return montage_path, stats_path


def _load_camera_images(camera_dir: Path, max_images: int = 6) -> List[Path]:
    if not camera_dir.exists():
        return []
    paths = sorted(
        [
            *camera_dir.glob("*.png"),
            *camera_dir.glob("*.jpg"),
            *camera_dir.glob("*.jpeg"),
        ]
    )
    if len(paths) <= max_images:
        return paths
    indices = np.linspace(0, len(paths) - 1, max_images).round().astype(int)
    return [paths[int(index)] for index in indices]


def _fit_image(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    width, height = size
    src = image.convert("RGB")
    scale = min(width / src.width, height / src.height)
    resized = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (238, 241, 245))
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def _make_final_with_camera(result_dir: Path, cloud_montage_path: Path, camera_dir: Path) -> Path:
    cloud = Image.open(cloud_montage_path).convert("RGB")
    camera_paths = _load_camera_images(camera_dir)
    thumb_w, thumb_h = 300, 225
    bottom_h = 360 if camera_paths else 96
    final = Image.new("RGB", (cloud.width, cloud.height + bottom_h), (243, 246, 249))
    final.paste(cloud, (0, 0))
    draw = ImageDraw.Draw(final)
    title_font = _load_font(23)
    label_font = _load_font(15)
    y0 = cloud.height + 20
    draw.text((28, y0), "Matching camera frames sampled from the same bag", fill=(13, 27, 42), font=title_font)

    if camera_paths:
        gap = 14
        start_x = 28
        y_img = y0 + 46
        for index, path in enumerate(camera_paths[:6]):
            try:
                thumb = _fit_image(Image.open(path), (thumb_w, thumb_h))
            except OSError:
                continue
            x = start_x + index * (thumb_w + gap)
            final.paste(thumb, (x, y_img))
            draw.rectangle([x, y_img, x + thumb_w - 1, y_img + thumb_h - 1], outline=(178, 187, 199))
            draw.text((x + 4, y_img + thumb_h + 7), path.name, fill=(46, 58, 72), font=label_font)
    else:
        draw.text((28, y0 + 50), "No camera preview frames found.", fill=(160, 52, 44), font=label_font)

    out = result_dir / "final_static_full_extent_with_camera.png"
    final.save(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--pcd", default=None, type=Path)
    parser.add_argument("--camera-dir", default=None, type=Path)
    args = parser.parse_args()

    result_dir = args.result_dir
    pcd_path = args.pcd or result_dir / "all_raw_points.pcd"
    camera_dir = args.camera_dir or result_dir / "camera_preview"
    points, colors, metadata = _read_pcd_xyz_rgb(pcd_path)
    if len(points) == 0:
        raise RuntimeError(f"No finite points in {pcd_path}")
    montage_path, stats_path = _make_cloud_montage(result_dir, points, colors, metadata)
    final_path = _make_final_with_camera(result_dir, montage_path, camera_dir)

    print(f"PCD={pcd_path}")
    print(f"POINTS={len(points)}")
    print(f"MONTAGE={montage_path}")
    print(f"STATS={stats_path}")
    print(f"FINAL={final_path}")


if __name__ == "__main__":
    main()
