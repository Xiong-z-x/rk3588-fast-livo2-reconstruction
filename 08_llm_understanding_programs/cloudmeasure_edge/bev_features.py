from __future__ import annotations

import numpy as np


def encode_bev_pillar_tensor(
    points: np.ndarray,
    bbox_min: tuple[float, float, float],
    bbox_max: tuple[float, float, float],
    grid_size: int,
) -> tuple[np.ndarray, dict[str, object]]:
    finite = points[np.isfinite(points).all(axis=1)].astype(np.float32, copy=False)
    if len(finite) < 32:
        raise ValueError("Not enough finite points to encode BEV tensor")

    lo = np.asarray(bbox_min, dtype=np.float32)
    hi = np.asarray(bbox_max, dtype=np.float32)
    span = np.maximum(hi - lo, 1e-6)

    xy = (finite[:, :2] - lo[:2]) / span[:2]
    xi = np.floor(xy[:, 0] * grid_size).astype(np.int32)
    yi = np.floor(xy[:, 1] * grid_size).astype(np.int32)
    inside = (xi >= 0) & (xi < grid_size) & (yi >= 0) & (yi < grid_size)
    selected = finite[inside]
    xi = xi[inside]
    yi = yi[inside]
    flat = yi * grid_size + xi
    cell_count = grid_size * grid_size

    counts = np.bincount(flat, minlength=cell_count).astype(np.float32)
    z = selected[:, 2]
    z_sum = np.bincount(flat, weights=z, minlength=cell_count).astype(np.float32)
    z2_sum = np.bincount(flat, weights=z * z, minlength=cell_count).astype(np.float32)
    x_sum = np.bincount(flat, weights=selected[:, 0], minlength=cell_count).astype(np.float32)
    y_sum = np.bincount(flat, weights=selected[:, 1], minlength=cell_count).astype(np.float32)

    z_max = np.full(cell_count, -np.inf, dtype=np.float32)
    z_min = np.full(cell_count, np.inf, dtype=np.float32)
    np.maximum.at(z_max, flat, z)
    np.minimum.at(z_min, flat, z)

    valid = counts > 0
    density = np.zeros(cell_count, dtype=np.float32)
    density[valid] = np.log1p(counts[valid])
    if np.max(density) > 0:
        density /= np.max(density)

    z_mean = np.zeros(cell_count, dtype=np.float32)
    z_std = np.zeros(cell_count, dtype=np.float32)
    x_mean = np.zeros(cell_count, dtype=np.float32)
    y_mean = np.zeros(cell_count, dtype=np.float32)
    z_mean[valid] = z_sum[valid] / counts[valid]
    x_mean[valid] = x_sum[valid] / counts[valid]
    y_mean[valid] = y_sum[valid] / counts[valid]
    z_std[valid] = np.sqrt(np.maximum(z2_sum[valid] / counts[valid] - z_mean[valid] ** 2, 0))
    z_max[~valid] = lo[2]
    z_min[~valid] = lo[2]

    channels = np.stack(
        (
            density.reshape(grid_size, grid_size),
            ((z_max - lo[2]) / span[2]).reshape(grid_size, grid_size),
            ((z_min - lo[2]) / span[2]).reshape(grid_size, grid_size),
            ((z_mean - lo[2]) / span[2]).reshape(grid_size, grid_size),
            (z_std / max(float(span[2]), 1e-6)).reshape(grid_size, grid_size),
            ((x_mean - lo[0]) / span[0]).reshape(grid_size, grid_size),
            ((y_mean - lo[1]) / span[1]).reshape(grid_size, grid_size),
            valid.astype(np.float32).reshape(grid_size, grid_size),
        ),
        axis=0,
    )
    tensor = np.clip(channels, 0, 1).astype(np.float32)[None, ...]
    metadata = {
        "gridSize": grid_size,
        "featureShape": list(tensor.shape),
        "pointCount": int(len(finite)),
        "encodedPointCount": int(len(selected)),
        "nonEmptyCells": int(np.sum(valid)),
        "bboxMin": lo.tolist(),
        "bboxMax": hi.tolist(),
    }
    return tensor, metadata
