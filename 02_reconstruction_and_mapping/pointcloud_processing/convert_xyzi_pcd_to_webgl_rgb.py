#!/usr/bin/env python3
"""Convert FAST-LIVO2 XYZI-style binary PCD into WebGL x y z rgb PCD."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import numpy as np


OUT_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("rgb", "<u4")])


def _read_header(path: Path) -> Tuple[int, int, Dict[str, str]]:
    header: Dict[str, str] = {}
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise RuntimeError(f"{path} ended before DATA line")
            text = line.decode("ascii", errors="replace").strip()
            if text:
                parts = text.split(maxsplit=1)
                if len(parts) == 2:
                    header[parts[0]] = parts[1]
            if text == "DATA binary":
                return handle.tell(), int(header.get("POINTS", header.get("WIDTH", "0"))), header


def _point_step(header: Dict[str, str]) -> int:
    sizes = [int(value) for value in header["SIZE"].split()]
    counts = [int(value) for value in header.get("COUNT", " ".join(["1"] * len(sizes))).split()]
    return sum(size * count for size, count in zip(sizes, counts))


def _pack_intensity_rgb(intensity: np.ndarray) -> np.ndarray:
    finite = intensity[np.isfinite(intensity)]
    if finite.size:
        lo = float(np.percentile(finite, 1))
        hi = float(np.percentile(finite, 99))
    else:
        lo, hi = 0.0, 1.0
    scale = max(hi - lo, 1e-6)
    t = np.clip((intensity.astype(np.float32) - lo) / scale, 0.0, 1.0)
    # Dark blue -> cyan -> yellow, readable on white background.
    r = np.clip(35 + 220 * t, 0, 255).astype(np.uint8)
    g = np.clip(80 + 155 * np.sqrt(t), 0, 255).astype(np.uint8)
    b = np.clip(190 - 145 * t, 0, 255).astype(np.uint8)
    return ((r.astype(np.uint32) & 255) << 16) | ((g.astype(np.uint32) & 255) << 8) | (b.astype(np.uint32) & 255)


def convert(src: Path, dst: Path, chunk_points: int) -> Dict[str, object]:
    offset, points, header = _read_header(src)
    fields = header.get("FIELDS", "").split()
    if "x" not in fields or "y" not in fields or "z" not in fields or "intensity" not in fields:
        raise RuntimeError(f"{src.name} lacks x/y/z/intensity fields: {fields}")
    step = _point_step(header)
    expected = offset + points * step
    if src.stat().st_size != expected:
        raise RuntimeError(f"{src.name} size mismatch: expected {expected}, got {src.stat().st_size}")
    if any(value != "4" for value in header.get("SIZE", "").split()):
        raise RuntimeError(f"{src.name} contains non-4-byte fields, unsupported by this converter")

    field_index = {name: idx for idx, name in enumerate(fields)}
    floats_per_point = step // 4
    data = np.memmap(src, dtype="<f4", mode="r", offset=offset, shape=(points, floats_per_point))
    intensity = np.asarray(data[:, field_index["intensity"]], dtype=np.float32)
    rgb = _pack_intensity_rgb(intensity)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as handle:
        handle.write(
            (
                "# .PCD v0.7 - Point Cloud Data file format\n"
                "VERSION 0.7\n"
                "FIELDS x y z rgb\n"
                "SIZE 4 4 4 4\n"
                "TYPE F F F U\n"
                "COUNT 1 1 1 1\n"
                f"WIDTH {points}\n"
                "HEIGHT 1\n"
                "VIEWPOINT 0 0 0 1 0 0 0\n"
                f"POINTS {points}\n"
                "DATA binary\n"
            ).encode("ascii")
        )
        out = np.empty(min(chunk_points, points), dtype=OUT_DTYPE)
        for start in range(0, points, chunk_points):
            end = min(points, start + chunk_points)
            n = end - start
            chunk = data[start:end]
            out_view = out[:n]
            out_view["x"] = chunk[:, field_index["x"]]
            out_view["y"] = chunk[:, field_index["y"]]
            out_view["z"] = chunk[:, field_index["z"]]
            out_view["rgb"] = rgb[start:end]
            handle.write(out_view.tobytes())

    xyz = data[:, [field_index["x"], field_index["y"], field_index["z"]]]
    mins = np.min(xyz, axis=0).astype(float).tolist()
    maxs = np.max(xyz, axis=0).astype(float).tolist()
    return {"points": points, "bytes": dst.stat().st_size, "bboxMin": mins, "bboxMax": maxs}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--dst", required=True, type=Path)
    parser.add_argument("--chunk-points", type=int, default=1_000_000)
    args = parser.parse_args()
    print(convert(args.src, args.dst, args.chunk_points))


if __name__ == "__main__":
    main()
