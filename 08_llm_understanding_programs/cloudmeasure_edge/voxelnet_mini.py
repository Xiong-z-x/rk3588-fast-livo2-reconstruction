from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import VoxelNetConfig
from .rknn_runtime import RknnRuntime


@dataclass(frozen=True)
class RecognitionResult:
    label: str
    confidence: float
    logits: list[float]
    model: str = "voxelnet-mini"


class VoxelNetMiniRecognizer:
    def __init__(self, model_path: str | Path, config: VoxelNetConfig) -> None:
        self.model_path = Path(model_path)
        self.config = config
        self.runtime = RknnRuntime(self.model_path, core_mask="core0_1_2")

    def load(self) -> None:
        self.runtime.load()

    def close(self) -> None:
        self.runtime.close()

    def recognize(self, points: np.ndarray) -> RecognitionResult:
        tensor = self._voxelize(points)
        outputs = self.runtime.infer([tensor])
        if not outputs:
            raise ValueError("VoxelNet-Mini RKNN model returned no outputs")
        logits = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        if logits.size < len(self.config.labels):
            raise ValueError(
                f"VoxelNet-Mini output has {logits.size} logits, expected {len(self.config.labels)}"
            )
        logits = logits[: len(self.config.labels)]
        probabilities = _softmax(logits)
        index = int(np.argmax(probabilities))
        return RecognitionResult(
            label=self.config.labels[index],
            confidence=float(probabilities[index]),
            logits=[float(value) for value in logits],
        )

    def _voxelize(self, points: np.ndarray) -> np.ndarray:
        if len(points) < 16:
            raise ValueError("Not enough points for VoxelNet-Mini recognition")
        centered = points - np.median(points, axis=0)
        scale = np.maximum(np.ptp(centered, axis=0), self.config.voxel_size_m)
        normalized = (centered / scale) + 0.5
        grid = np.asarray(self.config.grid_shape, dtype=np.int32)
        indices = np.floor(normalized * grid).astype(np.int32)
        inside = np.all((indices >= 0) & (indices < grid), axis=1)
        indices = indices[inside]
        selected = centered[inside]

        if len(indices) == 0:
            raise ValueError("No points remain inside VoxelNet grid")

        ix, iy, iz = indices[:, 0], indices[:, 1], indices[:, 2]
        counts = np.zeros((grid[2], grid[1], grid[0]), dtype=np.float32)
        z_max = np.full_like(counts, -np.inf)
        x_sum = np.zeros_like(counts)
        y_sum = np.zeros_like(counts)
        np.add.at(counts, (iz, iy, ix), 1.0)
        np.maximum.at(z_max, (iz, iy, ix), selected[:, 2])
        np.add.at(x_sum, (iz, iy, ix), selected[:, 0])
        np.add.at(y_sum, (iz, iy, ix), selected[:, 1])

        occupied = counts > 0
        density = np.zeros_like(counts)
        density[occupied] = np.log1p(counts[occupied])
        if np.max(density) > 0:
            density /= np.max(density)
        z_feature = np.zeros_like(counts)
        z_feature[occupied] = z_max[occupied]
        x_mean = np.zeros_like(counts)
        y_mean = np.zeros_like(counts)
        x_mean[occupied] = x_sum[occupied] / np.maximum(counts[occupied], 1.0)
        y_mean[occupied] = y_sum[occupied] / np.maximum(counts[occupied], 1.0)

        tensor = np.stack((density, z_feature, x_mean, y_mean), axis=0)
        return tensor[None, ...].astype(np.float32)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / np.maximum(np.sum(exp), 1e-9)
