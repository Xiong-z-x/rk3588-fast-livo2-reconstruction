#!/usr/bin/env python3
"""Create a per-Livox-scan frame index for progressive WebGL playback."""

from __future__ import annotations

import argparse
import bisect
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import rosbag


def _read_lidar_poses(path: Path) -> Tuple[List[float], List[List[float]], List[List[float]]]:
    times: List[float] = []
    positions: List[List[float]] = []
    quaternions: List[List[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        values = [float(value) for value in parts[:8]]
        times.append(values[0])
        positions.append(values[1:4])
        quaternions.append(values[4:8])
    if not times:
        raise RuntimeError(f"No lidar poses found in {path}")
    return times, positions, quaternions


def _nearest_pose_index(times: Sequence[float], stamp: float) -> Tuple[int, float]:
    pos = bisect.bisect_left(times, stamp)
    best_idx = -1
    best_dt = float("inf")
    for idx in (pos - 1, pos):
        if 0 <= idx < len(times):
            dt = abs(times[idx] - stamp)
            if dt < best_dt:
                best_idx = idx
                best_dt = dt
    if best_idx < 0:
        raise RuntimeError("No nearest pose")
    return best_idx, best_dt


def _finite_point_count(points: Sequence[Any]) -> int:
    count = 0
    for point in points:
        if math.isfinite(point.x) and math.isfinite(point.y) and math.isfinite(point.z):
            count += 1
    return count


def create_index(
    *,
    bag_path: Path,
    poses_path: Path,
    source_pcd: Path,
    out_json: Path,
    topic: str,
    max_pose_dt: float,
) -> Dict[str, Any]:
    pose_times, pose_xyz, pose_q = _read_lidar_poses(poses_path)
    frames: List[Dict[str, Any]] = []
    pose_dts: List[float] = []
    frame_total = 0
    unmatched = 0
    first_stamp: float | None = None

    with rosbag.Bag(str(bag_path), "r") as bag:
        for _topic, msg, _bag_stamp in bag.read_messages(topics=[topic]):
            scan_index = frame_total
            frame_total += 1

            points = getattr(msg, "points", [])
            if not points:
                continue
            point_count = _finite_point_count(points)
            if point_count <= 0:
                continue

            stamp = float(msg.header.stamp.to_sec())
            pose_index, pose_dt = _nearest_pose_index(pose_times, stamp)
            if pose_dt > max_pose_dt:
                unmatched += 1
                continue

            if first_stamp is None:
                first_stamp = stamp
            pose_dts.append(float(pose_dt))
            frames.append(
                {
                    "frame_index": len(frames),
                    "scan_index": scan_index,
                    "stamp": stamp,
                    "pose_time": float(pose_times[pose_index]),
                    "rel_time": stamp - first_stamp,
                    "pose_dt": float(pose_dt),
                    "pose_index": int(pose_index),
                    "point_count": int(point_count),
                    "position": [float(value) for value in pose_xyz[pose_index]],
                    "quaternion_xyzw": [float(value) for value in pose_q[pose_index]],
                }
            )

    duration = float(frames[-1]["rel_time"]) if frames else 0.0
    total_points = int(sum(frame["point_count"] for frame in frames))
    data: Dict[str, Any] = {
        "source_bag": str(bag_path),
        "source_poses": str(poses_path),
        "source_pcd": str(source_pcd),
        "topic": topic,
        "max_pose_dt_threshold": max_pose_dt,
        "frame_total": frame_total,
        "matched_frames": len(frames),
        "unmatched_frames": unmatched,
        "pose_count": len(pose_times),
        "total_points": total_points,
        "duration": duration,
        "duration_sec": duration,
        "max_pose_dt": max(pose_dts) if pose_dts else None,
        "max_pose_match_dt": max(pose_dts) if pose_dts else None,
        "mean_pose_dt": sum(pose_dts) / len(pose_dts) if pose_dts else None,
        "frames": frames,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, type=Path)
    parser.add_argument("--poses", required=True, type=Path)
    parser.add_argument("--source-pcd", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--topic", default="/livox/lidar")
    parser.add_argument("--max-pose-dt", default=0.12, type=float)
    args = parser.parse_args()

    data = create_index(
        bag_path=args.bag,
        poses_path=args.poses,
        source_pcd=args.source_pcd,
        out_json=args.out_json,
        topic=args.topic,
        max_pose_dt=args.max_pose_dt,
    )
    print(
        json.dumps(
            {
                "out_json": str(args.out_json),
                "frame_total": data["frame_total"],
                "matched_frames": data["matched_frames"],
                "unmatched_frames": data["unmatched_frames"],
                "total_points": data["total_points"],
                "duration_sec": data["duration_sec"],
                "max_pose_dt": data["max_pose_dt"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
