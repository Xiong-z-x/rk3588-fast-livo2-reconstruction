#!/usr/bin/env python3
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import rosbag


TOPICS = [
    "/livox/lidar",
    "/livox/imu",
    "/hikrobot_camera/rgb",
    "/hikrobot_camera/camera_info",
]


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <bag>", file=sys.stderr)
        return 2
    bag_path = Path(sys.argv[1])
    series = {topic: [] for topic in TOPICS}
    with rosbag.Bag(str(bag_path), "r") as bag:
        for topic, msg, bag_time in bag.read_messages(topics=TOPICS):
            if hasattr(msg, "header") and msg.header.stamp.to_sec() > 0:
                series[topic].append((bag_time.to_sec(), msg.header.stamp.to_sec()))

    if not series["/livox/lidar"]:
        print("no lidar data", file=sys.stderr)
        return 3

    base_bag = series["/livox/lidar"][0][0]
    base_header = series["/livox/lidar"][0][1]
    print("# arrival delay = bag_rel_time - header_rel_time, using first lidar as origin")
    print(f"bag={bag_path}")
    print(f"base_bag={base_bag:.9f}")
    print(f"base_header={base_header:.9f}")

    for topic in TOPICS:
        rows = series[topic]
        delays = [(bag_t - base_bag) - (header_t - base_header) for bag_t, header_t in rows]
        header_times = [header_t for _, header_t in rows]
        header_dts = [header_times[i + 1] - header_times[i] for i in range(len(header_times) - 1)]
        print(f"\n[{topic}]")
        print(
            "count=%d delay_min=%.6f delay_med=%.6f delay_p95=%.6f delay_max=%.6f"
            % (
                len(rows),
                min(delays),
                statistics.median(delays),
                sorted(delays)[int(0.95 * (len(delays) - 1))],
                max(delays),
            )
        )

        periods = []
        start = None
        last = None
        for index, (bag_t, header_t) in enumerate(rows):
            delay = (bag_t - base_bag) - (header_t - base_header)
            if delay > 1.0:
                if start is None:
                    start = index
                last = index
            else:
                if start is not None:
                    periods.append((start, last))
                    start = None
                    last = None
        if start is not None:
            periods.append((start, last))

        print(f"delay_gt_1s_periods={len(periods)}")
        for begin, end in periods[:8]:
            bag_begin, header_begin = rows[begin]
            bag_end, header_end = rows[end]
            print(
                "  idx=%d-%d header_rel=%.3f->%.3f bag_rel=%.3f->%.3f "
                "delay=%.3f->%.3f count=%d"
                % (
                    begin,
                    end,
                    header_begin - base_header,
                    header_end - base_header,
                    bag_begin - base_bag,
                    bag_end - base_bag,
                    (bag_begin - base_bag) - (header_begin - base_header),
                    (bag_end - base_bag) - (header_end - base_header),
                    end - begin + 1,
                )
            )

        if header_dts:
            imax = max(range(len(header_dts)), key=lambda i: header_dts[i])
            print(
                "max_header_gap idx=%d header_rel=%.3f->%.3f dt=%.6f "
                "bag_rel=%.3f->%.3f bag_dt=%.6f"
                % (
                    imax,
                    header_times[imax] - base_header,
                    header_times[imax + 1] - base_header,
                    header_dts[imax],
                    rows[imax][0] - base_bag,
                    rows[imax + 1][0] - base_bag,
                    rows[imax + 1][0] - rows[imax][0],
                )
            )

    for topic in ["/hikrobot_camera/rgb", "/hikrobot_camera/camera_info"]:
        rows = series[topic]
        groups = []
        i = 0
        while i < len(rows):
            j = i
            while j + 1 < len(rows) and abs(rows[j + 1][1] - rows[i][1]) < 1e-9:
                j += 1
            if j > i:
                groups.append((i, j))
            i = j + 1

        print(f"\n[DUPLICATE_HEADER_GROUPS {topic}] count={len(groups)}")
        for begin, end in sorted(groups, key=lambda pair: pair[1] - pair[0], reverse=True)[:10]:
            bag_begin, header_time = rows[begin]
            bag_end, _ = rows[end]
            print(
                "  idx=%d-%d repeat=%d header_rel=%.3f bag_rel=%.3f->%.3f "
                "bag_duration=%.3fs"
                % (
                    begin,
                    end,
                    end - begin + 1,
                    header_time - base_header,
                    bag_begin - base_bag,
                    bag_end - base_bag,
                    bag_end - bag_begin,
                )
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
