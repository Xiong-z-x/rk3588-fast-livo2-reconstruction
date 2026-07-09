#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudmeasure_edge.bev_yolo_detector import BevYoloCargoDetector, BevYoloDetection
from cloudmeasure_edge.config import load_config
from cloudmeasure_edge.geometry import OrientedBox
from cloudmeasure_edge.pcd_io import crop_roi, load_xyz


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/edge_runtime.yaml")
    parser.add_argument("--pcd", required=True)
    parser.add_argument("--bbox-min", nargs=3, type=float, required=True)
    parser.add_argument("--bbox-max", nargs=3, type=float, required=True)
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    if config.models.bev_yolo_pt is None:
        raise SystemExit("models.bev_yolo_pt is not configured")

    model_path = _resolve_runtime_path(config_path, config.models.bev_yolo_pt)
    points = load_xyz(args.pcd)
    roi = crop_roi(points, tuple(args.bbox_min), tuple(args.bbox_max))
    detector = BevYoloCargoDetector(model_path, config.bev_yolo)
    detections, metadata = detector.detect(roi, tuple(args.bbox_min), tuple(args.bbox_max))
    detector.close()

    print(
        json.dumps(
            {
                "pcdPath": str(Path(args.pcd).expanduser()),
                "roiPointCount": int(len(roi)),
                "metadata": metadata,
                "detections": [_detection_to_dict(item) for item in detections],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _resolve_runtime_path(config_path: Path, candidate: Path) -> Path:
    if candidate.is_absolute():
        return candidate
    return (config_path.parent.parent / candidate).resolve()


def _detection_to_dict(detection: BevYoloDetection) -> dict:
    payload = {
        "id": detection.detection_id,
        "label": detection.label,
        "confidence": round(detection.confidence, 6),
        "xyxyPixels": detection.xyxy_pixels,
        "xyxyMeters": detection.xyxy_meters,
        "pointCount": detection.point_count,
    }
    if detection.box is not None:
        payload["box"] = _box_to_dict(detection.box)
    return payload


def _box_to_dict(box: OrientedBox) -> dict:
    return {
        "center": [float(v) for v in box.center],
        "dimensions": [float(v) for v in box.dimensions],
        "yaw": float(box.yaw),
        "volumeM3": float(box.volume),
    }


if __name__ == "__main__":
    main()
