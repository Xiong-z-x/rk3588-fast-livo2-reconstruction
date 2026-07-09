from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OrientedBox:
    center: np.ndarray
    axes: np.ndarray
    dimensions: np.ndarray
    yaw: float

    @property
    def volume(self) -> float:
        return float(np.prod(self.dimensions))

    def world_to_local(self, points: np.ndarray) -> np.ndarray:
        return (points - self.center) @ self.axes

    def local_to_world(self, points: np.ndarray) -> np.ndarray:
        return points @ self.axes.T + self.center


def fit_oriented_box(points: np.ndarray, quantile: float = 1.5) -> OrientedBox:
    if len(points) < 16:
        raise ValueError("Not enough points to fit OBB")

    center_xy = np.median(points[:, :2], axis=0)
    centered_xy = points[:, :2] - center_xy
    covariance = np.cov(centered_xy, rowvar=False)
    _, eigenvectors = np.linalg.eigh(covariance)
    axes_xy = eigenvectors[:, ::-1]

    projected_xy = centered_xy @ axes_xy
    qlo_xy = np.percentile(projected_xy, quantile, axis=0)
    qhi_xy = np.percentile(projected_xy, 100 - quantile, axis=0)
    zlo, zhi = np.percentile(points[:, 2], [quantile, 100 - quantile])

    dimensions = np.maximum(
        np.array([qhi_xy[0] - qlo_xy[0], qhi_xy[1] - qlo_xy[1], zhi - zlo], dtype=np.float32),
        1e-4,
    )
    local_center_xy = (qlo_xy + qhi_xy) / 2
    world_center_xy = center_xy + local_center_xy @ axes_xy.T
    center = np.array([world_center_xy[0], world_center_xy[1], (zlo + zhi) / 2], dtype=np.float32)

    axes = np.eye(3, dtype=np.float32)
    axes[:2, :2] = axes_xy.astype(np.float32)
    yaw = float(np.arctan2(axes_xy[1, 0], axes_xy[0, 0]))

    return OrientedBox(center=center, axes=axes, dimensions=dimensions, yaw=yaw)


def sample_points_in_obb(box: OrientedBox, count: int, seed: int = 17) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    half = box.dimensions / 2
    local = rng.uniform(-half, half, size=(count, 3)).astype(np.float32)
    return box.local_to_world(local).astype(np.float32), box.volume / max(count, 1)


def points_inside_obb(points: np.ndarray, box: OrientedBox, margin: float = 1.02) -> np.ndarray:
    local = box.world_to_local(points)
    half = box.dimensions / 2 * margin
    return np.all(np.abs(local) <= half, axis=1)
