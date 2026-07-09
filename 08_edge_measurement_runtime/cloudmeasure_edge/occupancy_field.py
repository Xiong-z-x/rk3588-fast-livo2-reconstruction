from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .config import OccupancyConfig
from .geometry import OrientedBox, sample_points_in_obb


class OccupancyMLP(nn.Module):
    def __init__(self, hidden_dim: int = 128, depth: int = 5) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        in_dim = 9
        for layer_index in range(depth):
            layers.append(nn.Linear(in_dim if layer_index == 0 else hidden_dim, hidden_dim))
            layers.append(nn.ReLU(inplace=True))
        layers.append(nn.Linear(hidden_dim, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, query_xyz: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        if context.ndim == 1:
            context = context[None, :].expand(query_xyz.shape[0], -1)
        features = torch.cat((query_xyz, context[:, :6]), dim=1)
        return self.network(features).squeeze(-1)


@dataclass(frozen=True)
class VolumeResult:
    occupied_volume_m3: float
    obb_volume_m3: float
    occupancy_ratio: float
    occupied_sample_count: int
    sample_count: int
    threshold: float


class NeuralOccupancyVolumeEstimator:
    def __init__(self, checkpoint_path: str | Path, config: OccupancyConfig, device: str | None = None) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.config = config
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model: OccupancyMLP | None = None

    def load(self) -> None:
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Occupancy checkpoint not found: {self.checkpoint_path}")
        try:
            checkpoint = torch.load(self.checkpoint_path, map_location=self.device, weights_only=True)
        except TypeError:
            checkpoint = torch.load(self.checkpoint_path, map_location=self.device)
        model_args = checkpoint.get("model_args", {})
        model = OccupancyMLP(
            hidden_dim=int(model_args.get("hidden_dim", 128)),
            depth=int(model_args.get("depth", 5)),
        ).to(self.device)
        state_dict = checkpoint.get("state_dict", checkpoint)
        model.load_state_dict(state_dict)
        model.eval()
        self.model = model

    def estimate(self, object_points: np.ndarray, box: OrientedBox) -> VolumeResult:
        if self.model is None:
            self.load()
        assert self.model is not None

        samples, sample_volume = sample_points_in_obb(
            box,
            self.config.samples_per_object,
            seed=max(1, len(object_points)),
        )
        local_samples = box.world_to_local(samples).astype(np.float32)
        half = np.maximum(box.dimensions / 2, 1e-6)
        normalized_samples = local_samples / half
        context = _object_context(object_points, box)

        occupied_count = 0
        probability_sum = 0.0
        batch_size = self.config.batch_size
        with torch.no_grad():
            for start in range(0, len(normalized_samples), batch_size):
                batch = torch.from_numpy(normalized_samples[start : start + batch_size]).to(self.device)
                ctx = torch.from_numpy(context).to(self.device)
                logits = self.model(batch, ctx)
                probabilities = torch.sigmoid(logits)
                occupied_count += int(torch.sum(probabilities >= self.config.occupancy_threshold).item())
                probability_sum += float(torch.sum(probabilities).item())

        occupancy_ratio = probability_sum / max(len(normalized_samples), 1)
        occupied_volume = occupancy_ratio * box.volume
        return VolumeResult(
            occupied_volume_m3=float(occupied_volume),
            obb_volume_m3=box.volume,
            occupancy_ratio=float(occupancy_ratio),
            occupied_sample_count=occupied_count,
            sample_count=int(len(normalized_samples)),
            threshold=float(self.config.occupancy_threshold),
        )


def _object_context(points: np.ndarray, box: OrientedBox) -> np.ndarray:
    local = box.world_to_local(points)
    mean = np.mean(local, axis=0)
    std = np.std(local, axis=0)
    return np.concatenate((mean, std)).astype(np.float32)
