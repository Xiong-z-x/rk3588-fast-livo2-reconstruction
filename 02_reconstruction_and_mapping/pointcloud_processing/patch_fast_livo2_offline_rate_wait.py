#!/usr/bin/env python3
from pathlib import Path
import shutil


SCRIPT = Path("/root/fast_livo2_runs/run_fast_livo2_offline_bag.sh")
BACKUP = Path("/root/fast_livo2_runs/run_fast_livo2_offline_bag.sh.bak_20260609_rate_wait")


def main() -> None:
    if not SCRIPT.exists():
        raise FileNotFoundError(SCRIPT)
    if not BACKUP.exists():
        shutil.copy2(SCRIPT, BACKUP)

    text = SCRIPT.read_text()
    if "FAST_LIVO2_PLAY_RATE" not in text:
        text = text.replace(
            'LAUNCH_FILE="$RUN_DIR/mapping_mid360_offline_save.launch"\n',
            'LAUNCH_FILE="$RUN_DIR/mapping_mid360_offline_save.launch"\n'
            'PLAY_RATE="${FAST_LIVO2_PLAY_RATE:-0.5}"\n'
            'POST_PLAY_WAIT_SEC="${FAST_LIVO2_POST_PLAY_WAIT_SEC:-60}"\n',
        )
        text = text.replace(
            'echo "[INFO] playing rosbag"\n'
            'rosbag play --clock "$BAG_PATH" --topics',
            'echo "[INFO] playing rosbag rate=${PLAY_RATE}"\n'
            'rosbag play --clock -r "$PLAY_RATE" "$BAG_PATH" --topics',
        )
        text = text.replace(
            'echo "[INFO] waiting for FAST-LIVO2 to consume buffered data"\n'
            'sleep 10\n',
            'echo "[INFO] waiting ${POST_PLAY_WAIT_SEC}s for FAST-LIVO2 to consume buffered data"\n'
            'sleep "$POST_PLAY_WAIT_SEC"\n',
        )
        SCRIPT.write_text(text)
        SCRIPT.chmod(0o755)

    for line_no, line in enumerate(SCRIPT.read_text().splitlines(), start=1):
        if (
            "PLAY_RATE" in line
            or "POST_PLAY_WAIT" in line
            or "rosbag play --clock" in line
            or ("waiting " in line and "FAST-LIVO2" in line)
        ):
            print(f"{line_no}:{line}")


if __name__ == "__main__":
    main()
