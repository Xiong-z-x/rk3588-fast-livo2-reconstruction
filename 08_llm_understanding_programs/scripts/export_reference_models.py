#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudmeasure_edge.occupancy_field import OccupancyMLP


class BevCargoSegNet(nn.Module):
    def __init__(self, in_channels: int = 8) -> None:
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Conv2d(in_channels, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 96, 3, padding=1),
            nn.BatchNorm2d(96),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(96, 64, 2, stride=2),
            nn.ReLU(inplace=True),
        )
        self.heatmap = nn.Conv2d(64, 1, 1)
        self.offset = nn.Conv2d(64, 2, 1)
        self.dimensions = nn.Sequential(nn.Conv2d(64, 3, 1), nn.Softplus())
        self.yaw = nn.Conv2d(64, 1, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        feature = self.backbone(x)
        return self.heatmap(feature), self.offset(feature), self.dimensions(feature), self.yaw(feature)


class VoxelNetMini(nn.Module):
    def __init__(self, class_count: int = 3) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv3d(4, 16, 3, padding=1),
            nn.BatchNorm3d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(2),
            nn.Conv3d(16, 32, 3, padding=1),
            nn.BatchNorm3d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(2),
            nn.Conv3d(32, 64, 3, padding=1),
            nn.BatchNorm3d(64),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool3d(1),
        )
        self.classifier = nn.Linear(64, class_count)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feature = self.encoder(x).flatten(1)
        return self.classifier(feature)


def export_models(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    seg_model = BevCargoSegNet().eval()
    seg_input = torch.zeros(1, 8, 512, 512)
    torch.onnx.export(
        seg_model,
        seg_input,
        output_dir / "cargo_instance_seg.onnx",
        input_names=["bev_features"],
        output_names=["heatmap", "offset", "dimensions", "yaw"],
        opset_version=12,
    )

    voxelnet = VoxelNetMini(class_count=3).eval()
    voxel_input = torch.zeros(1, 4, 32, 32, 32)
    torch.onnx.export(
        voxelnet,
        voxel_input,
        output_dir / "voxelnet_mini_cargo_cls.onnx",
        input_names=["voxel_tensor"],
        output_names=["class_logits"],
        opset_version=12,
    )

    occupancy = OccupancyMLP(hidden_dim=128, depth=5)
    torch.save(
        {
            "model_args": {"hidden_dim": 128, "depth": 5},
            "state_dict": occupancy.state_dict(),
        },
        output_dir / "neural_occupancy_field.pt",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="models/exported")
    args = parser.parse_args()
    export_models(Path(args.output_dir))


if __name__ == "__main__":
    main()
