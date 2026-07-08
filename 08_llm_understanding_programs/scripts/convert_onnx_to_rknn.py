#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def convert_onnx_to_rknn(
    onnx_path: Path,
    rknn_path: Path,
    dataset_path: Path | None,
    target_platform: str,
    mean_values: list[list[float]] | None,
    std_values: list[list[float]] | None,
) -> None:
    try:
        from rknn.api import RKNN
    except Exception as exc:  # pragma: no cover - RKNN Toolkit is board/vendor specific
        raise RuntimeError("RKNN Toolkit is required: pip install rknn-toolkit2") from exc

    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX file not found: {onnx_path}")
    if dataset_path is not None and not dataset_path.exists():
        raise FileNotFoundError(f"Quantization dataset not found: {dataset_path}")

    rknn_path.parent.mkdir(parents=True, exist_ok=True)
    rknn = RKNN(verbose=True)
    ret = rknn.config(
        target_platform=target_platform,
        mean_values=mean_values,
        std_values=std_values,
        optimization_level=3,
    )
    if ret != 0:
        raise RuntimeError(f"RKNN config failed: {ret}")

    ret = rknn.load_onnx(model=str(onnx_path))
    if ret != 0:
        raise RuntimeError(f"RKNN load_onnx failed: {ret}")

    ret = rknn.build(
        do_quantization=dataset_path is not None,
        dataset=str(dataset_path) if dataset_path else None,
    )
    if ret != 0:
        raise RuntimeError(f"RKNN build failed: {ret}")

    ret = rknn.export_rknn(str(rknn_path))
    if ret != 0:
        raise RuntimeError(f"RKNN export failed: {ret}")
    rknn.release()


def parse_channel_values(text: str | None) -> list[list[float]] | None:
    if not text:
        return None
    return [[float(item) for item in text.split(",")]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--rknn", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--target-platform", default="rk3588")
    parser.add_argument("--mean-values")
    parser.add_argument("--std-values")
    args = parser.parse_args()

    convert_onnx_to_rknn(
        onnx_path=Path(args.onnx),
        rknn_path=Path(args.rknn),
        dataset_path=Path(args.dataset) if args.dataset else None,
        target_platform=args.target_platform,
        mean_values=parse_channel_values(args.mean_values),
        std_values=parse_channel_values(args.std_values),
    )


if __name__ == "__main__":
    main()
