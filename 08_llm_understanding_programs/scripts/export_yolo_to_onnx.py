#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="models/third_party/yolo/yolov8n.pt")
    parser.add_argument("--output", default="models/exported/bev_yolo_yolov8n.onnx")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--opset", type=int, default=12)
    parser.add_argument("--dynamic", action="store_true")
    parser.add_argument("--no-simplify", action="store_true")
    args = parser.parse_args()

    weights = Path(args.weights).expanduser().resolve()
    if not weights.is_file():
        raise FileNotFoundError(f"YOLO weights not found: {weights}")

    try:
        from ultralytics import YOLO
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("ultralytics is required to export YOLO weights to ONNX") from exc

    model = YOLO(str(weights))
    exported = Path(
        model.export(
            format="onnx",
            imgsz=args.imgsz,
            opset=args.opset,
            simplify=not args.no_simplify,
            dynamic=args.dynamic,
        )
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if exported.resolve() != output:
        shutil.move(str(exported), output)
    print(output)


if __name__ == "__main__":
    main()
