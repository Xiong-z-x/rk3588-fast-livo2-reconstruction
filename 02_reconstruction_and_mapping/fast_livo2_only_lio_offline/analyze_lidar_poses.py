#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def _percentile(values: np.ndarray, value: float) -> float:
    return float(np.percentile(values, value)) if values.size else 0.0


def analyze(path: Path) -> dict[str, Any]:
    data = np.loadtxt(path, dtype=np.float64, ndmin=2)
    if data.shape[1] < 8:
        raise RuntimeError(f"Expected at least 8 columns in {path}, got {data.shape[1]}")
    if data.shape[0] < 2:
        raise RuntimeError(f"Expected at least 2 poses in {path}, got {data.shape[0]}")

    time = data[:, 0]
    position = data[:, 1:4]
    quaternion = data[:, 4:8]
    dt = np.diff(time)
    step = np.linalg.norm(np.diff(position, axis=0), axis=1)
    quaternion_norm = np.linalg.norm(quaternion, axis=1)
    normalized = quaternion / np.maximum(quaternion_norm[:, None], 1e-12)
    dots = np.abs(np.sum(normalized[:-1] * normalized[1:], axis=1))
    rotation_deg = np.degrees(2.0 * np.arccos(np.clip(dots, 0.0, 1.0)))
    valid_dt = dt > 1e-9
    speed = np.divide(step, dt, out=np.full_like(step, np.inf), where=valid_dt)

    flags: list[str] = []
    duplicate_time = int(np.count_nonzero(np.abs(dt) <= 1e-9))
    negative_time = int(np.count_nonzero(dt < -1e-9))
    if duplicate_time:
        flags.append(f"duplicate_time={duplicate_time}")
    if negative_time:
        flags.append(f"negative_time={negative_time}")
    if float(np.max(dt)) > 0.25:
        flags.append(f"pose_dt_max={float(np.max(dt)):.6f}s")
    if float(np.max(step)) > 0.50:
        flags.append(f"translation_step_max={float(np.max(step)):.6f}m")
    if float(np.max(rotation_deg)) > 30.0:
        flags.append(f"rotation_step_max={float(np.max(rotation_deg)):.6f}deg")
    quaternion_norm_error = float(np.max(np.abs(quaternion_norm - 1.0)))
    if quaternion_norm_error > 0.05:
        flags.append(f"quaternion_norm_error_max={quaternion_norm_error:.6f}")

    return {
        "status": "WARN" if flags else "PASS",
        "flags": flags,
        "pose_count": int(time.size),
        "pose_start": float(time[0]),
        "pose_end": float(time[-1]),
        "pose_duration_sec": float(time[-1] - time[0]),
        "duplicate_time": duplicate_time,
        "negative_time": negative_time,
        "pose_dt_min_sec": float(np.min(dt)),
        "pose_dt_median_sec": float(np.median(dt)),
        "pose_dt_p95_sec": _percentile(dt, 95),
        "pose_dt_max_sec": float(np.max(dt)),
        "path_length_m": float(np.sum(step)),
        "translation_step_median_m": float(np.median(step)),
        "translation_step_p95_m": _percentile(step, 95),
        "translation_step_max_m": float(np.max(step)),
        "translation_step_gt_0_25m": int(np.count_nonzero(step > 0.25)),
        "translation_step_gt_0_50m": int(np.count_nonzero(step > 0.50)),
        "speed_p95_mps": _percentile(speed[np.isfinite(speed)], 95),
        "speed_max_mps": float(np.max(speed[np.isfinite(speed)])),
        "rotation_step_median_deg": float(np.median(rotation_deg)),
        "rotation_step_p95_deg": _percentile(rotation_deg, 95),
        "rotation_step_max_deg": float(np.max(rotation_deg)),
        "rotation_step_gt_15deg": int(np.count_nonzero(rotation_deg > 15.0)),
        "rotation_step_gt_30deg": int(np.count_nonzero(rotation_deg > 30.0)),
        "quaternion_norm_error_max": quaternion_norm_error,
        "position_min_xyz_m": np.min(position, axis=0).tolist(),
        "position_max_xyz_m": np.max(position, axis=0).tolist(),
        "displacement_m": float(np.linalg.norm(position[-1] - position[0])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poses", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    args = parser.parse_args()

    result = analyze(args.poses)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    args.output_prefix.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_prefix.with_suffix(".txt").write_text(
        "\n".join(
            f"{key}={json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value}"
            for key, value in result.items()
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
