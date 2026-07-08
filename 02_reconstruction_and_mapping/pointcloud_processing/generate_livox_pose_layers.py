#!/usr/bin/env python3
"""Generate raw Livox and pose-mapped LiDAR PCD layers for WebGL review."""

from __future__ import annotations

import argparse
import bisect
import json
import math
import struct
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import rosbag


PCD_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("rgb", "<u4")])


def _pack_rgb(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    return ((r.astype(np.uint32) & 255) << 16) | ((g.astype(np.uint32) & 255) << 8) | (b.astype(np.uint32) & 255)


def _write_binary_pcd(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.empty(len(xyz), dtype=PCD_DTYPE)
    data["x"] = xyz[:, 0].astype(np.float32)
    data["y"] = xyz[:, 1].astype(np.float32)
    data["z"] = xyz[:, 2].astype(np.float32)
    data["rgb"] = rgb.astype(np.uint32)
    header = (
        "# .PCD v0.7 - Point Cloud Data file format\n"
        "VERSION 0.7\n"
        "FIELDS x y z rgb\n"
        "SIZE 4 4 4 4\n"
        "TYPE F F F U\n"
        "COUNT 1 1 1 1\n"
        f"WIDTH {len(xyz)}\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {len(xyz)}\n"
        "DATA binary\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        handle.write(data.tobytes())


def _stride_arrays(xyz: np.ndarray, rgb: np.ndarray, stride: int) -> Tuple[np.ndarray, np.ndarray]:
    if stride <= 1:
        return xyz, rgb
    return xyz[::stride].copy(), rgb[::stride].copy()


def _bbox(xyz: np.ndarray) -> List[float]:
    if len(xyz) == 0:
        return []
    mins = xyz.min(axis=0)
    maxs = xyz.max(axis=0)
    return [float(mins[0]), float(mins[1]), float(mins[2]), float(maxs[0]), float(maxs[1]), float(maxs[2])]


def _reflectivity_rgb(reflectivity: np.ndarray) -> np.ndarray:
    val = np.clip(reflectivity.astype(np.float32), 0, 120) / 120.0
    # Light cyan-to-amber ramp, close to the previous engineering viewer.
    r = (55 + 200 * val).astype(np.uint8)
    g = (110 + 125 * np.sqrt(val)).astype(np.uint8)
    b = (130 + 75 * (1.0 - val)).astype(np.uint8)
    return _pack_rgb(r, g, b)


def _height_rgb(z: np.ndarray) -> np.ndarray:
    if len(z) == 0:
        return np.zeros((0,), dtype=np.uint32)
    lo = float(np.percentile(z, 1))
    hi = float(np.percentile(z, 99))
    denom = max(hi - lo, 1e-6)
    t = np.clip((z.astype(np.float32) - lo) / denom, 0, 1)
    # Blue -> cyan -> green -> yellow -> red height ramp.
    r = np.clip(255 * np.maximum(0, np.minimum(1, 1.5 * t - 0.25)), 0, 255).astype(np.uint8)
    g = np.clip(255 * np.maximum(0, np.minimum(1, 1.5 - np.abs(2.0 * t - 1.0))), 0, 255).astype(np.uint8)
    b = np.clip(255 * np.maximum(0, np.minimum(1, 1.25 - 1.7 * t)), 0, 255).astype(np.uint8)
    return _pack_rgb(r, g, b)


def _read_lidar_poses(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: List[List[float]] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 8:
            rows.append([float(value) for value in parts[:8]])
    if not rows:
        raise RuntimeError(f"No lidar poses in {path}")
    arr = np.asarray(rows, dtype=np.float64)
    return arr[:, 0], arr[:, 1:4], arr[:, 4:8]


def _quat_xyzw_to_rot(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-12:
        return np.eye(3)
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return np.array(
        [
            [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
            [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
            [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def _nearest_pose_index(times: Sequence[float], stamp: float) -> Tuple[int, float]:
    pos = bisect.bisect_left(times, stamp)
    best = None
    for idx in (pos - 1, pos):
        if 0 <= idx < len(times):
            dt = abs(times[idx] - stamp)
            if best is None or dt < best[1]:
                best = (idx, dt)
    if best is None:
        raise RuntimeError("No nearest pose")
    return best


def _collect_livox_arrays(
    bag_path: Path,
    topic: str,
    max_pose_dt: float,
    pose_times: np.ndarray | None = None,
    pose_xyz: np.ndarray | None = None,
    pose_q: np.ndarray | None = None,
) -> Tuple[np.ndarray, np.ndarray, dict]:
    xyz_parts: List[np.ndarray] = []
    reflect_parts: List[np.ndarray] = []
    frame_total = 0
    matched = 0
    unmatched = 0
    pose_dts: List[float] = []

    with rosbag.Bag(str(bag_path), "r") as bag:
        for _, msg, _ in bag.read_messages(topics=[topic]):
            frame_total += 1
            pts = msg.points
            if not pts:
                continue
            local = np.asarray([(p.x, p.y, p.z) for p in pts], dtype=np.float32)
            reflect = np.asarray([p.reflectivity for p in pts], dtype=np.float32)
            finite = np.isfinite(local).all(axis=1)
            local = local[finite]
            reflect = reflect[finite]
            if len(local) == 0:
                continue

            if pose_times is not None and pose_xyz is not None and pose_q is not None:
                stamp = msg.header.stamp.to_sec()
                idx, dt = _nearest_pose_index(pose_times.tolist(), stamp)
                if dt > max_pose_dt:
                    unmatched += 1
                    continue
                rot = _quat_xyzw_to_rot(pose_q[idx])
                world = (rot @ local.astype(np.float64).T).T + pose_xyz[idx]
                xyz_parts.append(world.astype(np.float32))
                pose_dts.append(float(dt))
                matched += 1
            else:
                xyz_parts.append(local)
            reflect_parts.append(reflect)

    if xyz_parts:
        xyz = np.concatenate(xyz_parts, axis=0)
        reflectivity = np.concatenate(reflect_parts, axis=0)
    else:
        xyz = np.empty((0, 3), dtype=np.float32)
        reflectivity = np.empty((0,), dtype=np.float32)

    summary = {
        "bag": str(bag_path),
        "topic": topic,
        "frame_total": frame_total,
        "valid_points": int(len(xyz)),
        "bbox_xyz": _bbox(xyz),
        "matched_frames": matched if pose_times is not None else None,
        "unmatched_frames": unmatched if pose_times is not None else None,
        "pose_match_dt_mean": float(np.mean(pose_dts)) if pose_dts else None,
        "pose_match_dt_max": float(np.max(pose_dts)) if pose_dts else None,
    }
    return xyz, reflectivity, summary


def _trajectory_points(pose_xyz: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if len(pose_xyz) == 0:
        return np.empty((0, 3), dtype=np.float32), np.empty((0,), dtype=np.uint32)
    points: List[np.ndarray] = []
    for point in pose_xyz:
        points.append(point.astype(np.float32))
        points.append(point.astype(np.float32))
    xyz = np.asarray(points, dtype=np.float32)
    rgb = np.full(len(xyz), (255 << 16) | (40 << 8) | 40, dtype=np.uint32)
    return xyz, rgb


def _write_stats(path: Path, summary: dict) -> None:
    path.write_text("\n".join(f"{k}={v}" for k, v in summary.items()) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, type=Path)
    parser.add_argument("--poses", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--topic", default="/livox/lidar")
    parser.add_argument("--view-stride", default=10, type=int)
    parser.add_argument("--max-pose-dt", default=0.12, type=float)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pose_times, pose_xyz, pose_q = _read_lidar_poses(args.poses)

    raw_xyz, raw_reflect, raw_summary = _collect_livox_arrays(args.bag, args.topic, args.max_pose_dt)
    raw_rgb = _reflectivity_rgb(raw_reflect)
    raw_full = args.out_dir / "livox_lidar_raw_accum_full.pcd"
    raw_view = args.out_dir / "livox_lidar_raw_accum_view_stride10.pcd"
    _write_binary_pcd(raw_full, raw_xyz, raw_rgb)
    view_xyz, view_rgb = _stride_arrays(raw_xyz, raw_rgb, args.view_stride)
    _write_binary_pcd(raw_view, view_xyz, view_rgb)
    raw_summary.update(
        {
            "source": "/livox/lidar raw accumulated, no FAST-LIVO2 pose/color",
            "view_stride": args.view_stride,
            "view_points": int(len(view_xyz)),
            "reflectivity_mean": float(np.mean(raw_reflect)) if len(raw_reflect) else None,
            "reflectivity_p50": float(np.percentile(raw_reflect, 50)) if len(raw_reflect) else None,
            "reflectivity_p90": float(np.percentile(raw_reflect, 90)) if len(raw_reflect) else None,
        }
    )
    _write_stats(args.out_dir / "livox_lidar_raw_accum_stats.txt", raw_summary)

    mapped_xyz, _mapped_reflect, mapped_summary = _collect_livox_arrays(
        args.bag,
        args.topic,
        args.max_pose_dt,
        pose_times=pose_times,
        pose_xyz=pose_xyz,
        pose_q=pose_q,
    )
    mapped_rgb = _height_rgb(mapped_xyz[:, 2]) if len(mapped_xyz) else np.empty((0,), dtype=np.uint32)
    mapped_full = args.out_dir / "lidar_pose_mapped_height_full.pcd"
    mapped_view = args.out_dir / "lidar_pose_mapped_height_view_stride10.pcd"
    _write_binary_pcd(mapped_full, mapped_xyz, mapped_rgb)
    view_xyz, view_rgb = _stride_arrays(mapped_xyz, mapped_rgb, args.view_stride)
    _write_binary_pcd(mapped_view, view_xyz, view_rgb)

    dt = np.diff(pose_times)
    step = np.linalg.norm(np.diff(pose_xyz, axis=0), axis=1) if len(pose_xyz) > 1 else np.empty((0,))
    mapped_summary.update(
        {
            "source": "/livox/lidar transformed by FAST-LIVO2 lidar_poses.txt",
            "color": "height_gradient, no camera RGB",
            "pose_count": int(len(pose_times)),
            "pose_start": float(pose_times[0]),
            "pose_end": float(pose_times[-1]),
            "pose_duration": float(pose_times[-1] - pose_times[0]),
            "view_stride": args.view_stride,
            "view_points": int(len(view_xyz)),
            "path_length": float(step.sum()) if len(step) else 0.0,
            "step_max": float(step.max()) if len(step) else 0.0,
            "pose_dt_max": float(dt.max()) if len(dt) else 0.0,
        }
    )
    _write_stats(args.out_dir / "lidar_pose_mapped_height_stats.txt", mapped_summary)

    traj_xyz, traj_rgb = _trajectory_points(pose_xyz)
    _write_binary_pcd(args.out_dir / "lidar_pose_trajectory_points.pcd", traj_xyz, traj_rgb)

    print(
        json.dumps(
            {
                "raw_points": int(len(raw_xyz)),
                "mapped_points": int(len(mapped_xyz)),
                "trajectory_points": int(len(traj_xyz)),
                "raw_full": str(raw_full),
                "mapped_full": str(mapped_full),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
