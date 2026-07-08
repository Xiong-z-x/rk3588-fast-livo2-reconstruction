#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import rospy
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header


def _read_pcd_binary_xyz_rgb(path: Path) -> Tuple[bytes, int, Dict[str, str]]:
    header: Dict[str, str] = {}
    header_lines = []

    with path.open("rb") as f:
        while True:
            raw_line = f.readline()
            if not raw_line:
                raise ValueError("PCD header ended before DATA line")
            line = raw_line.decode("ascii", errors="replace").strip()
            header_lines.append(line)
            if not line or line.startswith("#"):
                continue
            key, *rest = line.split(maxsplit=1)
            header[key.upper()] = rest[0] if rest else ""
            if key.upper() == "DATA":
                break
        data = f.read()

    if header.get("DATA", "").lower() != "binary":
        raise ValueError(f"Only binary PCD is supported, got DATA={header.get('DATA')!r}")

    required = {
        "FIELDS": "x y z rgb",
        "SIZE": "4 4 4 4",
        "TYPE": "F F F U",
        "COUNT": "1 1 1 1",
    }
    for key, expected in required.items():
        got = " ".join(header.get(key, "").split())
        if got != expected:
            raise ValueError(f"Unsupported PCD {key}: expected {expected!r}, got {got!r}")

    points = int(header["POINTS"])
    expected_bytes = points * 16
    if len(data) < expected_bytes:
        raise ValueError(f"PCD data is truncated: expected {expected_bytes}, got {len(data)}")
    if len(data) > expected_bytes:
        data = data[:expected_bytes]

    return data, points, header


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a binary xyzrgb PCD as one latched ROS1 PointCloud2.")
    parser.add_argument("pcd", type=Path)
    parser.add_argument("--topic", default="/static_all_raw_points")
    parser.add_argument("--frame-id", default="camera_init")
    parser.add_argument("--node-name", default="static_pcd_latched_publisher")
    args = parser.parse_args()

    data, points, _ = _read_pcd_binary_xyz_rgb(args.pcd)

    rospy.init_node(args.node_name, anonymous=False)
    pub = rospy.Publisher(args.topic, PointCloud2, queue_size=1, latch=True)

    msg = PointCloud2()
    msg.header = Header(frame_id=args.frame_id, stamp=rospy.Time.now())
    msg.height = 1
    msg.width = points
    msg.fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name="rgb", offset=12, datatype=PointField.UINT32, count=1),
    ]
    msg.is_bigendian = False
    msg.point_step = 16
    msg.row_step = msg.point_step * points
    msg.data = data
    msg.is_dense = False

    rospy.loginfo("Publishing %d points from %s to %s frame_id=%s", points, args.pcd, args.topic, args.frame_id)
    pub.publish(msg)
    rospy.spin()


if __name__ == "__main__":
    main()
