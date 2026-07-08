#!/usr/bin/env python3
"""Publish an accumulated colored PointCloud2 from a FAST-LIVO output bag."""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import rospy
import rosbag
from sensor_msgs import point_cloud2
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header


VoxelKey = Tuple[int, int, int]
PointValue = Tuple[float, float, float, int]


def decode_rgb_to_uint(value: object) -> int:
    if isinstance(value, float):
        return struct.unpack("<I", struct.pack("<f", value))[0] & 0x00FFFFFF
    return int(value) & 0x00FFFFFF


def load_voxel_cloud(
    bag_path: Path,
    topic: str,
    voxel: float,
    max_frames: int,
    frame_stride: int,
    point_stride: int,
) -> Tuple[np.ndarray, int, int]:
    voxels: Dict[VoxelKey, PointValue] = {}
    raw_points = 0
    used_frames = 0

    with rosbag.Bag(str(bag_path), "r") as bag:
        for frame_index, (_, msg, _) in enumerate(bag.read_messages(topics=[topic])):
            if frame_stride > 1 and frame_index % frame_stride != 0:
                continue
            if max_frames > 0 and used_frames >= max_frames:
                break
            used_frames += 1
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
                rgb = decode_rgb_to_uint(point[3]) if len(point) >= 4 else 0x50A0FF
                key = (
                    int(math.floor(x / voxel)),
                    int(math.floor(y / voxel)),
                    int(math.floor(z / voxel)),
                )
                voxels[key] = (x, y, z, rgb)

    if not voxels:
        raise RuntimeError(f"No valid points found in {bag_path} topic {topic}")
    arr = np.asarray(list(voxels.values()), dtype=np.float32)
    return arr, raw_points, used_frames


def make_cloud_msg(points_rgb: np.ndarray, frame_id: str) -> PointCloud2:
    header = Header()
    header.stamp = rospy.Time.now()
    header.frame_id = frame_id
    fields = [
        PointField("x", 0, PointField.FLOAT32, 1),
        PointField("y", 4, PointField.FLOAT32, 1),
        PointField("z", 8, PointField.FLOAT32, 1),
        PointField("rgb", 12, PointField.FLOAT32, 1),
    ]
    points = []
    for x, y, z, rgb_value in points_rgb:
        rgb_float = struct.unpack("<f", struct.pack("<I", int(rgb_value) & 0x00FFFFFF))[0]
        points.append((float(x), float(y), float(z), rgb_float))
    return point_cloud2.create_cloud(header, fields, points)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, type=Path)
    parser.add_argument("--source-topic", default="/cloud_registered")
    parser.add_argument("--publish-topic", default="/official_static_map")
    parser.add_argument("--frame-id", default="map")
    parser.add_argument("--voxel", type=float, default=0.12)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--point-stride", type=int, default=1)
    args = parser.parse_args()

    rospy.init_node("fast_livo_static_cloud_publisher", anonymous=False)
    rospy.loginfo("Loading static cloud from %s topic %s", args.bag, args.source_topic)
    points_rgb, raw_points, used_frames = load_voxel_cloud(
        args.bag,
        args.source_topic,
        args.voxel,
        args.max_frames,
        args.frame_stride,
        args.point_stride,
    )
    mins = points_rgb[:, :3].min(axis=0)
    maxs = points_rgb[:, :3].max(axis=0)
    rospy.loginfo(
        "Loaded static cloud: frames=%d raw_points=%d voxel_points=%d voxel=%.3f extent=[%.2f %.2f %.2f]..[%.2f %.2f %.2f]",
        used_frames,
        raw_points,
        len(points_rgb),
        args.voxel,
        mins[0],
        mins[1],
        mins[2],
        maxs[0],
        maxs[1],
        maxs[2],
    )
    publisher = rospy.Publisher(args.publish_topic, PointCloud2, queue_size=1, latch=True)
    cloud_msg = make_cloud_msg(points_rgb, args.frame_id)
    rate = rospy.Rate(0.5)
    while not rospy.is_shutdown():
        cloud_msg.header.stamp = rospy.Time.now()
        publisher.publish(cloud_msg)
        rate.sleep()


if __name__ == "__main__":
    main()
