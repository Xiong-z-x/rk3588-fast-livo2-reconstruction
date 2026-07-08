#!/usr/bin/env python3
"""Convert an ASCII PLY with x y z r g b fields to an ASCII PCD."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


def convert(ply: Path, pcd: Path) -> tuple[int, int]:
    raw = ply.read_bytes()
    header_end = raw.find(b"end_header\n")
    if header_end < 0:
        raise ValueError(f"bad PLY header: {ply}")
    header_end += len(b"end_header\n")
    header = raw[:header_end].decode("ascii", errors="replace").splitlines()

    vertex_count: int | None = None
    fmt: str | None = None

    for line in header:
        if line.startswith("format"):
            fmt = line.split()[1]
        if line.startswith("element vertex"):
            vertex_count = int(line.split()[-1])

    if vertex_count is None or fmt is None:
        raise ValueError(f"bad PLY header: {ply}")

    points: list[tuple[float, float, float, int]] = []
    if fmt == "ascii":
        lines = raw[header_end:].decode("utf-8", errors="replace").splitlines()
        for line in lines[:vertex_count]:
            vals = line.split()
            if len(vals) < 6:
                continue
            x, y, z = map(float, vals[:3])
            r, g, b = map(int, vals[3:6])
            rgb = (r << 16) | (g << 8) | b
            points.append((x, y, z, rgb))
    elif fmt == "binary_little_endian":
        stride = struct.calcsize("<fffBBB")
        payload = raw[header_end:]
        expected = vertex_count * stride
        if len(payload) < expected:
            raise ValueError(f"binary payload shorter than expected: {len(payload)} < {expected}")
        unpack = struct.Struct("<fffBBB").unpack_from
        for i in range(vertex_count):
            x, y, z, r, g, b = unpack(payload, i * stride)
            rgb = (r << 16) | (g << 8) | b
            points.append((x, y, z, rgb))
    else:
        raise ValueError(f"unsupported PLY format: {fmt}")

    with pcd.open("w", encoding="ascii") as f:
        f.write("# .PCD v0.7 - Point Cloud Data file format\n")
        f.write("VERSION 0.7\n")
        f.write("FIELDS x y z rgb\n")
        f.write("SIZE 4 4 4 4\n")
        f.write("TYPE F F F U\n")
        f.write("COUNT 1 1 1 1\n")
        f.write(f"WIDTH {len(points)}\n")
        f.write("HEIGHT 1\n")
        f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
        f.write(f"POINTS {len(points)}\n")
        f.write("DATA ascii\n")
        for x, y, z, rgb in points:
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {rgb}\n")

    return len(points), pcd.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ply", type=Path)
    parser.add_argument("pcd", type=Path)
    args = parser.parse_args()
    count, size = convert(args.ply, args.pcd)
    print(f"PCD_WRITTEN {args.pcd} points={count} bytes={size}")


if __name__ == "__main__":
    main()
