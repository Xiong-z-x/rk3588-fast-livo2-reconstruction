#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/noetic/setup.bash

python3 - <<'PY'
import os
import signal
import time


def iter_processes():
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="replace") as handle:
                comm = handle.read().strip()
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                cmdline = handle.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        yield pid, comm, cmdline


print("=== BEFORE CLEAN ===")
for pid, comm, cmdline in iter_processes():
    if comm in {"rviz", "roscore", "rosmaster"} or "publish_static_cloud_from_bag.py" in cmdline:
        print(pid, comm, cmdline[:240])

for pid, comm, cmdline in iter_processes():
    if comm == "rviz" or "publish_static_cloud_from_bag.py" in cmdline:
        try:
            os.kill(pid, signal.SIGTERM)
            print("killed", pid, comm)
        except ProcessLookupError:
            pass
        except OSError as exc:
            print("kill_failed", pid, comm, exc)

time.sleep(3)

print("=== AFTER CLEAN ===")
for pid, comm, cmdline in iter_processes():
    if comm in {"rviz", "roscore", "rosmaster"} or "publish_static_cloud_from_bag.py" in cmdline:
        print(pid, comm, cmdline[:240])
PY

if ! pgrep -x roscore >/dev/null 2>&1 && ! pgrep -x rosmaster >/dev/null 2>&1; then
  mkdir -p /root/fast_livo_runs/official_dataset_test/ntu_viral_eee03/restart_static_display
  nohup bash -lc "source /opt/ros/noetic/setup.bash; roscore" \
    > /root/fast_livo_runs/official_dataset_test/ntu_viral_eee03/restart_static_display/roscore.log 2>&1 &
  sleep 5
fi

run="$(cat /root/fast_livo_runs/official_dataset_test/ntu_viral_eee03/latest_run_dir.txt)"
view="/root/fast_livo_runs/official_dataset_test/ntu_viral_eee03/static_rviz_restart_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$view"

cat > "$view/start.sh" <<EOS
#!/usr/bin/env bash
export DISPLAY=:0
export QT_X11_NO_MITSHM=1
export LD_PRELOAD=/lib/aarch64-linux-gnu/libusb-1.0.so.0
source /opt/ros/noetic/setup.bash
source /root/fast_lio2_ws/devel/setup.bash
nohup /root/fast_livo_runs/scripts/publish_static_cloud_from_bag.py \\
  --bag "$run/fast_livo_outputs_eee03.bag" \\
  --source-topic /cloud_registered \\
  --publish-topic /official_static_map \\
  --frame-id map \\
  --voxel 0.12 \\
  > "$view/static_publisher.log" 2>&1 & echo \$! > "$view/static_publisher.pid"
sleep 20
nohup rviz -d /root/fast_livo_runs/scripts/fast_livo_static_map.rviz \\
  > "$view/rviz.log" 2>&1 & echo \$! > "$view/rviz.pid"
EOS

chmod +x "$view/start.sh"
nohup "$view/start.sh" > "$view/start.log" 2>&1 &
echo $! > "$view/start.pid"
ln -sfn "$view" /root/fast_livo_runs/official_dataset_test/ntu_viral_eee03/latest_static_rviz

printf "RESTART_VIEW_DIR=%s\n" "$view"
printf "START_PID=%s\n" "$(cat "$view/start.pid")"
