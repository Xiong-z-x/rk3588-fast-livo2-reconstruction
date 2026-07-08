#!/usr/bin/env python3
import argparse
import os

import rospy
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header


def build_message(bin_path: str, frame_id: str) -> PointCloud2:
    file_size = os.path.getsize(bin_path)
    point_step = 16
    if file_size % point_step != 0:
        raise RuntimeError(f"invalid XYZI file size {file_size}, not divisible by {point_step}")
    point_count = file_size // point_step
    with open(bin_path, "rb") as f:
        data = f.read()
    msg = PointCloud2()
    msg.header = Header(frame_id=frame_id)
    msg.height = 1
    msg.width = point_count
    msg.fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name="intensity", offset=12, datatype=PointField.FLOAT32, count=1),
    ]
    msg.is_bigendian = False
    msg.point_step = point_step
    msg.row_step = point_step * point_count
    msg.data = data
    msg.is_dense = False
    return msg


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bin_path")
    parser.add_argument("--topic", default="/livox/raw_accumulated_static")
    parser.add_argument("--frame-id", default="livox_frame")
    parser.add_argument("--rate", type=float, default=0.2)
    args = parser.parse_args()

    rospy.init_node("livox_raw_accumulated_static_publisher", anonymous=False)
    msg = build_message(args.bin_path, args.frame_id)
    pub = rospy.Publisher(args.topic, PointCloud2, queue_size=1, latch=True)
    rospy.loginfo("loaded raw accumulated XYZI cloud: path=%s points=%d", args.bin_path, msg.width)
    rospy.loginfo("publishing latched topic=%s frame_id=%s", args.topic, args.frame_id)
    rate = rospy.Rate(args.rate)
    while not rospy.is_shutdown():
        msg.header.stamp = rospy.Time.now()
        pub.publish(msg)
        rate.sleep()


if __name__ == "__main__":
    main()
