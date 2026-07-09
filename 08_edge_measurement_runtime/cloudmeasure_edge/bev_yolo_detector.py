from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .bev_features import encode_bev_pillar_tensor
from .config import BevYoloConfig
from .geometry import OrientedBox, fit_oriented_box


@dataclass(frozen=True)
class BevYoloDetection:
    detection_id: str
    label: str
    confidence: float
    xyxy_pixels: list[float]
    xyxy_meters: list[float]
    point_count: int
    box: OrientedBox | None


class BevYoloCargoDetector:
    """Runs a YOLO detector on a BEV projection of the point cloud ROI."""

    def __init__(self, model_path: str | Path, config: BevYoloConfig) -> None:
        self.model_path = Path(model_path)
        self.config = config
        self._model: Any | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        if not self.model_path.is_file():
            raise FileNotFoundError(f"YOLO model not found: {self.model_path}")
        try:
            from ultralytics import YOLO
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError("ultralytics is required for BEV-YOLO inference") from exc
        self._model = YOLO(str(self.model_path))

    def close(self) -> None:
        self._model = None

    def detect(
        self,
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> tuple[list[BevYoloDetection], dict[str, object]]:
        self.load()
        image, metadata = self.encode_bev_image(points, bbox_min, bbox_max)
        results = self._model.predict(  # type: ignore[union-attr]
            source=image,
            imgsz=self.config.grid_size,
            conf=self.config.confidence_threshold,
            max_det=self.config.max_detections,
            verbose=False,
        )
        detections = self._postprocess(results[0], points, bbox_min, bbox_max)
        metadata["modelPath"] = str(self.model_path)
        metadata["modelFamily"] = "Ultralytics YOLO"
        metadata["detectionCount"] = len(detections)
        return detections, metadata

    def encode_bev_image(
        self,
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> tuple[np.ndarray, dict[str, object]]:
        tensor, metadata = encode_bev_pillar_tensor(points, bbox_min, bbox_max, self.config.grid_size)
        channels = tensor[0]
        image = np.stack(
            (
                channels[0],
                channels[1],
                channels[7],
            ),
            axis=-1,
        )
        image_u8 = np.clip(image * 255.0, 0, 255).astype(np.uint8)
        metadata["bevYoloImageShape"] = list(image_u8.shape)
        metadata["bevYoloChannels"] = ["density", "normalized_z_max", "valid_cell"]
        return image_u8, metadata

    def _postprocess(
        self,
        result: Any,
        points: np.ndarray,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> list[BevYoloDetection]:
        if result.boxes is None or len(result.boxes) == 0:
            return []
        xyxy = result.boxes.xyxy.cpu().numpy()
        conf = result.boxes.conf.cpu().numpy()
        cls = result.boxes.cls.cpu().numpy().astype(int)
        names = getattr(result, "names", {}) or {}

        detections: list[BevYoloDetection] = []
        for index, (box_pixels, score, class_id) in enumerate(zip(xyxy, conf, cls, strict=True)):
            xyxy_meters = _pixels_to_meters(
                box_pixels,
                grid_size=self.config.grid_size,
                bbox_min=bbox_min,
                bbox_max=bbox_max,
            )
            selected = _points_in_xyxy(points, xyxy_meters)
            if len(selected) < self.config.min_points_per_detection:
                continue
            fitted_box: OrientedBox | None = fit_oriented_box(selected) if len(selected) >= 32 else None
            label = str(names.get(int(class_id), class_id))
            detections.append(
                BevYoloDetection(
                    detection_id=f"bev_yolo_{index + 1:02d}",
                    label=label,
                    confidence=float(score),
                    xyxy_pixels=[float(v) for v in box_pixels],
                    xyxy_meters=[float(v) for v in xyxy_meters],
                    point_count=int(len(selected)),
                    box=fitted_box,
                )
            )
        return detections


def _pixels_to_meters(
    xyxy_pixels: np.ndarray,
    grid_size: int,
    bbox_min: tuple[float, float, float],
    bbox_max: tuple[float, float, float],
) -> list[float]:
    lo = np.asarray(bbox_min, dtype=np.float32)
    hi = np.asarray(bbox_max, dtype=np.float32)
    span = np.maximum(hi - lo, 1e-6)
    x1, y1, x2, y2 = [float(v) for v in xyxy_pixels]
    return [
        float(lo[0] + (x1 / grid_size) * span[0]),
        float(lo[1] + (y1 / grid_size) * span[1]),
        float(lo[0] + (x2 / grid_size) * span[0]),
        float(lo[1] + (y2 / grid_size) * span[1]),
    ]


def _points_in_xyxy(points: np.ndarray, xyxy_meters: list[float]) -> np.ndarray:
    x1, y1, x2, y2 = xyxy_meters
    xmin, xmax = sorted((x1, x2))
    ymin, ymax = sorted((y1, y2))
    mask = (
        (points[:, 0] >= xmin)
        & (points[:, 0] <= xmax)
        & (points[:, 1] >= ymin)
        & (points[:, 1] <= ymax)
    )
    return points[mask].astype(np.float32, copy=False)
