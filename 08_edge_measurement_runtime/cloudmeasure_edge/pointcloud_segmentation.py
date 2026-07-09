from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .bev_features import encode_bev_pillar_tensor
from .config import SegmentationConfig
from .geometry import OrientedBox, fit_oriented_box
from .rknn_runtime import RknnRuntime


@dataclass(frozen=True)
class SegmentedInstance:
    instance_id: str
    points: np.ndarray
    score: float
    box: OrientedBox
    cell_count: int

    @property
    def obb_volume_m3(self) -> float:
        return self.box.volume


@dataclass(frozen=True)
class CenterHeadCandidate:
    y: int
    x: int
    score: float
    center_xy: tuple[float, float]
    dimensions: tuple[float, float, float]
    yaw: float


def _connected_components(mask: np.ndarray) -> list[np.ndarray]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[list[tuple[int, int]]] = []
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

    ys, xs = np.where(mask)
    for sy, sx in zip(ys, xs):
        if visited[sy, sx]:
            continue
        visited[sy, sx] = True
        queue: deque[tuple[int, int]] = deque([(int(sy), int(sx))])
        cells: list[tuple[int, int]] = []
        while queue:
            y, x = queue.popleft()
            cells.append((y, x))
            for dy, dx in neighbors:
                ny, nx = y + dy, x + dx
                if ny < 0 or ny >= height or nx < 0 or nx >= width:
                    continue
                if visited[ny, nx] or not mask[ny, nx]:
                    continue
                visited[ny, nx] = True
                queue.append((ny, nx))
        components.append(cells)

    return [np.asarray(component, dtype=np.int32) for component in components]


def _grid_indices(
    points: np.ndarray,
    bbox_min: tuple[float, float, float],
    bbox_max: tuple[float, float, float],
    grid_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lo = np.asarray(bbox_min, dtype=np.float32)
    hi = np.asarray(bbox_max, dtype=np.float32)
    span = np.maximum(hi - lo, 1e-6)
    xy = (points[:, :2] - lo[:2]) / span[:2]
    xi = np.floor(xy[:, 0] * grid_size).astype(np.int32)
    yi = np.floor(xy[:, 1] * grid_size).astype(np.int32)
    inside = (xi >= 0) & (xi < grid_size) & (yi >= 0) & (yi < grid_size)
    return yi, xi, inside


class CargoSegmentationNpu:
    def __init__(self, model_path: str | Path, config: SegmentationConfig) -> None:
        self.model_path = Path(model_path)
        self.config = config
        self.runtime = RknnRuntime(self.model_path, core_mask="core0_1_2")

    def load(self) -> None:
        self.runtime.load()

    def close(self) -> None:
        self.runtime.close()

    def infer_instances(
        self,
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> tuple[list[SegmentedInstance], dict[str, object]]:
        tensor, metadata = encode_bev_pillar_tensor(points, bbox_min, bbox_max, self.config.grid_size)
        outputs = self.runtime.infer([tensor])
        instances = self.postprocess(outputs, points, bbox_min, bbox_max)
        metadata["npuModel"] = str(self.model_path)
        metadata["instanceCount"] = len(instances)
        return instances, metadata

    def postprocess(
        self,
        outputs: list[np.ndarray],
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> list[SegmentedInstance]:
        if not outputs:
            raise ValueError("Segmentation RKNN model returned no output tensors")
        if len(outputs) >= 3:
            return self._postprocess_center_head(outputs, points, bbox_min, bbox_max)
        return self._postprocess_objectness(outputs, points, bbox_min, bbox_max)

    def _postprocess_objectness(
        self,
        outputs: list[np.ndarray],
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> list[SegmentedInstance]:
        logits = np.asarray(outputs[0])
        if logits.ndim == 4:
            logits = logits[0]
        if logits.ndim == 3:
            objectness = logits[0]
        elif logits.ndim == 2:
            objectness = logits
        else:
            raise ValueError(f"Unsupported segmentation output shape: {outputs[0].shape}")

        if objectness.shape[0] != self.config.grid_size or objectness.shape[1] != self.config.grid_size:
            objectness = _resize_nearest(objectness, self.config.grid_size)

        scores = _sigmoid(objectness)
        mask = scores >= self.config.score_threshold
        components = [
            component
            for component in _connected_components(mask)
            if len(component) >= self.config.min_component_cells
        ]
        components.sort(key=len, reverse=True)
        components = components[: self.config.max_instances]

        yi, xi, inside = _grid_indices(points, bbox_min, bbox_max, self.config.grid_size)
        point_cells = np.column_stack((yi, xi))
        instances: list[SegmentedInstance] = []
        for index, cells in enumerate(components):
            cell_keys = {tuple(cell) for cell in cells.tolist()}
            selected_mask = np.array(
                [inside[i] and tuple(point_cells[i]) in cell_keys for i in range(len(points))],
                dtype=bool,
            )
            component_points = points[selected_mask]
            if len(component_points) < 32:
                continue
            box = fit_oriented_box(component_points)
            score = float(np.mean(scores[cells[:, 0], cells[:, 1]]))
            instances.append(
                SegmentedInstance(
                    instance_id=f"cargo_{index + 1:02d}",
                    points=component_points.astype(np.float32, copy=False),
                    score=score,
                    box=box,
                    cell_count=int(len(cells)),
                )
            )
        if not instances:
            raise ValueError("Segmentation model produced no valid cargo instances")
        return instances

    def _postprocess_center_head(
        self,
        outputs: list[np.ndarray],
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> list[SegmentedInstance]:
        heatmap = _head_2d(outputs[0], channel=0, target_size=self.config.grid_size)
        offset = _head_chw(outputs[1], target_size=self.config.grid_size)
        dimensions = _head_chw(outputs[2], target_size=self.config.grid_size)
        yaw_map = _head_2d(outputs[3], channel=0, target_size=self.config.grid_size) if len(outputs) >= 4 else None
        scores = _sigmoid(heatmap)
        candidates = _center_head_candidates(
            scores=scores,
            offset=offset,
            dimensions=dimensions,
            yaw_map=yaw_map,
            bbox_min=bbox_min,
            bbox_max=bbox_max,
            score_threshold=self.config.score_threshold,
            max_instances=self.config.max_instances,
        )
        if not candidates:
            raise ValueError("Center-head segmentation produced no cargo candidates")

        instances: list[SegmentedInstance] = []
        consumed = np.zeros(len(points), dtype=bool)
        for index, candidate in enumerate(candidates):
            candidate_points = _points_for_candidate(points, candidate, consumed)
            if len(candidate_points) < 32:
                continue
            consumed |= _candidate_point_mask(points, candidate)
            box = fit_oriented_box(candidate_points)
            instances.append(
                SegmentedInstance(
                    instance_id=f"cargo_{index + 1:02d}",
                    points=candidate_points.astype(np.float32, copy=False),
                    score=candidate.score,
                    box=box,
                    cell_count=1,
                )
            )
        if not instances:
            raise ValueError("Center-head segmentation candidates did not map to valid point clusters")
        return instances


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if np.nanmin(values) >= 0 and np.nanmax(values) <= 1:
        return values
    return 1.0 / (1.0 + np.exp(-np.clip(values, -40, 40)))


def _resize_nearest(image: np.ndarray, target_size: int) -> np.ndarray:
    y_idx = np.floor(np.linspace(0, image.shape[0] - 1, target_size)).astype(np.int32)
    x_idx = np.floor(np.linspace(0, image.shape[1] - 1, target_size)).astype(np.int32)
    return image[np.ix_(y_idx, x_idx)]


def _head_chw(output: np.ndarray, target_size: int) -> np.ndarray:
    array = np.asarray(output, dtype=np.float32)
    if array.ndim == 4:
        array = array[0]
    if array.ndim == 2:
        array = array[None, ...]
    if array.ndim != 3:
        raise ValueError(f"Unsupported segmentation head shape: {output.shape}")
    if array.shape[-2:] != (target_size, target_size):
        array = np.stack([_resize_nearest(channel, target_size) for channel in array], axis=0)
    return array


def _head_2d(output: np.ndarray, channel: int, target_size: int) -> np.ndarray:
    chw = _head_chw(output, target_size)
    if channel >= chw.shape[0]:
        raise ValueError(f"Segmentation head channel {channel} missing from shape {chw.shape}")
    return chw[channel]


def _center_head_candidates(
    scores: np.ndarray,
    offset: np.ndarray,
    dimensions: np.ndarray,
    yaw_map: np.ndarray | None,
    bbox_min: tuple[float, float, float],
    bbox_max: tuple[float, float, float],
    score_threshold: float,
    max_instances: int,
) -> list[CenterHeadCandidate]:
    local_max = _local_maxima(scores)
    ys, xs = np.where((scores >= score_threshold) & local_max)
    order = np.argsort(scores[ys, xs])[::-1]
    lo = np.asarray(bbox_min, dtype=np.float32)
    hi = np.asarray(bbox_max, dtype=np.float32)
    span = np.maximum(hi - lo, 1e-6)
    candidates: list[CenterHeadCandidate] = []
    for item in order[: max_instances * 3]:
        y = int(ys[item])
        x = int(xs[item])
        dx = float(offset[0, y, x]) if offset.shape[0] >= 1 else 0.0
        dy = float(offset[1, y, x]) if offset.shape[0] >= 2 else 0.0
        center_x = float(lo[0] + ((x + 0.5 + dx) / scores.shape[1]) * span[0])
        center_y = float(lo[1] + ((y + 0.5 + dy) / scores.shape[0]) * span[1])
        dim_values = dimensions[:3, y, x] if dimensions.shape[0] >= 3 else np.array([0.6, 0.6, 1.0])
        dims = np.maximum(np.abs(dim_values.astype(np.float32)), np.array([0.15, 0.15, 0.15], dtype=np.float32))
        yaw = float(yaw_map[y, x]) if yaw_map is not None else 0.0
        candidate = CenterHeadCandidate(
            y=y,
            x=x,
            score=float(scores[y, x]),
            center_xy=(center_x, center_y),
            dimensions=(float(dims[0]), float(dims[1]), float(dims[2])),
            yaw=yaw,
        )
        if not _overlaps_existing(candidate, candidates):
            candidates.append(candidate)
        if len(candidates) >= max_instances:
            break
    return candidates


def _local_maxima(scores: np.ndarray) -> np.ndarray:
    padded = np.pad(scores, 1, mode="edge")
    maxima = np.ones_like(scores, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            maxima &= scores >= padded[1 + dy : 1 + dy + scores.shape[0], 1 + dx : 1 + dx + scores.shape[1]]
    return maxima


def _overlaps_existing(candidate: CenterHeadCandidate, existing: list[CenterHeadCandidate]) -> bool:
    cx, cy = candidate.center_xy
    radius = 0.35 * max(candidate.dimensions[0], candidate.dimensions[1])
    for other in existing:
        ox, oy = other.center_xy
        other_radius = 0.35 * max(other.dimensions[0], other.dimensions[1])
        if np.hypot(cx - ox, cy - oy) < max(radius, other_radius):
            return True
    return False


def _candidate_point_mask(points: np.ndarray, candidate: CenterHeadCandidate) -> np.ndarray:
    cx, cy = candidate.center_xy
    sx, sy, sz = candidate.dimensions
    z_center = float(np.median(points[:, 2]))
    cos_yaw = np.cos(candidate.yaw)
    sin_yaw = np.sin(candidate.yaw)
    dx = points[:, 0] - cx
    dy = points[:, 1] - cy
    local_x = dx * cos_yaw + dy * sin_yaw
    local_y = -dx * sin_yaw + dy * cos_yaw
    local_z = points[:, 2] - z_center
    return (
        (np.abs(local_x) <= sx * 0.62)
        & (np.abs(local_y) <= sy * 0.62)
        & (np.abs(local_z) <= sz * 0.70)
    )


def _points_for_candidate(
    points: np.ndarray,
    candidate: CenterHeadCandidate,
    consumed: np.ndarray,
) -> np.ndarray:
    mask = _candidate_point_mask(points, candidate) & ~consumed
    return points[mask]
