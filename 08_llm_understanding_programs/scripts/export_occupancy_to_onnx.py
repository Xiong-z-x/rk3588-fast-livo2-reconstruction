#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudmeasure_edge.occupancy_field import OccupancyMLP


def export_occupancy_to_onnx(checkpoint_path: Path, output_path: Path) -> None:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model_args = checkpoint.get("model_args", {})
    model = OccupancyMLP(
        hidden_dim=int(model_args.get("hidden_dim", 128)),
        depth=int(model_args.get("depth", 5)),
    ).eval()
    model.load_state_dict(checkpoint.get("state_dict", checkpoint))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    query_xyz = torch.zeros(8192, 3, dtype=torch.float32)
    context = torch.zeros(8192, 6, dtype=torch.float32)
    torch.onnx.export(
        model,
        (query_xyz, context),
        output_path,
        input_names=["query_xyz", "context"],
        output_names=["occupancy_logits"],
        dynamic_axes={
            "query_xyz": {0: "sample_count"},
            "context": {0: "sample_count"},
            "occupancy_logits": {0: "sample_count"},
        },
        opset_version=12,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", default="models/exported/neural_occupancy_field.onnx")
    args = parser.parse_args()
    export_occupancy_to_onnx(Path(args.checkpoint), Path(args.output))


if __name__ == "__main__":
    main()
