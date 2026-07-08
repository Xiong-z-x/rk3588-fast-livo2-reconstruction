from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from .config import RuntimeConfig, load_config
from .npu_monitor import NpuLoad, read_npu_load as read_configured_npu_load
from .occupancy_field import NeuralOccupancyVolumeEstimator, VolumeResult
from .pcd_io import crop_roi, load_xyz, read_pcd_header
from .pointcloud_segmentation import CargoSegmentationNpu, SegmentedInstance
from .voxelnet_mini import RecognitionResult, VoxelNetMiniRecognizer


@dataclass(frozen=True)
class CargoResult:
    id: str
    label: str
    confidence: float
    segmentation_score: float
    center: list[float]
    dimensions: list[float]
    yaw: float
    obb_volume_m3: float
    occupied_volume_m3: float
    occupancy_ratio: float
    point_count: int


@dataclass(frozen=True)
class PipelineOutput:
    pcd_path: str
    roi_point_count: int
    cargos: list[CargoResult]
    total_occupied_volume_m3: float
    total_obb_volume_m3: float
    npu_load: dict[str, Any] | None
    timing_ms: dict[str, float]
    feature_metadata: dict[str, Any]


class CloudMeasureEdgePipeline:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.segmenter = CargoSegmentationNpu(config.models.segmentation_rknn, config.segmentation)
        self.recognizer = VoxelNetMiniRecognizer(config.models.voxelnet_rknn, config.voxelnet)
        self.volume_estimator = NeuralOccupancyVolumeEstimator(
            config.models.occupancy_checkpoint,
            config.occupancy,
        )
        self._models_loaded = False

    def load_models(self) -> None:
        if self._models_loaded:
            return
        self.segmenter.load()
        self.recognizer.load()
        self.volume_estimator.load()
        self._models_loaded = True

    def close(self) -> None:
        self.segmenter.close()
        self.recognizer.close()
        self._models_loaded = False

    def run(
        self,
        pcd_path: str | Path,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
        read_npu_load: bool = True,
    ) -> PipelineOutput:
        started = perf_counter()
        self.load_models()
        resolved_pcd = self._validate_pcd_path(pcd_path)
        self._validate_bbox(bbox_min, bbox_max)
        load_started = perf_counter()
        points = load_xyz(resolved_pcd)
        roi = crop_roi(points, bbox_min, bbox_max)
        load_ms = (perf_counter() - load_started) * 1000

        seg_started = perf_counter()
        instances, feature_metadata = self.segmenter.infer_instances(roi, bbox_min, bbox_max)
        feature_metadata["occupancyRuntime"] = self.config.occupancy.runtime
        segmentation_ms = (perf_counter() - seg_started) * 1000

        cargo_results: list[CargoResult] = []
        recognize_ms = 0.0
        volume_ms = 0.0
        for instance in instances:
            rec_started = perf_counter()
            recognition = self.recognizer.recognize(instance.points)
            recognize_ms += (perf_counter() - rec_started) * 1000

            vol_started = perf_counter()
            volume = self.volume_estimator.estimate(instance.points, instance.box)
            volume_ms += (perf_counter() - vol_started) * 1000
            cargo_results.append(_cargo_result(instance, recognition, volume))

        npu_load: NpuLoad | None = None
        if read_npu_load:
            npu_load = read_configured_npu_load(self.config.board)

        return PipelineOutput(
            pcd_path=str(resolved_pcd),
            roi_point_count=int(len(roi)),
            cargos=cargo_results,
            total_occupied_volume_m3=float(sum(item.occupied_volume_m3 for item in cargo_results)),
            total_obb_volume_m3=float(sum(item.obb_volume_m3 for item in cargo_results)),
            npu_load=asdict(npu_load) if npu_load else None,
            timing_ms={
                "loadPcdMs": round(load_ms, 2),
                "segmentationNpuMs": round(segmentation_ms, 2),
                "voxelnetNpuMs": round(recognize_ms, 2),
                "occupancyFieldMs": round(volume_ms, 2),
                "totalMs": round((perf_counter() - started) * 1000, 2),
            },
            feature_metadata=feature_metadata,
        )

    def _validate_pcd_path(self, pcd_path: str | Path) -> Path:
        resolved = Path(pcd_path).expanduser().resolve()
        allowed_root = self.config.paths.allowed_pcd_root.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"PCD file not found: {resolved}")
        if allowed_root not in resolved.parents and resolved != allowed_root:
            raise ValueError(f"PCD path must be under allowed root: {allowed_root}")
        if resolved.suffix.lower() != ".pcd":
            raise ValueError(f"Only .pcd files are accepted: {resolved}")
        if resolved.stat().st_size > self.config.limits.max_pcd_bytes:
            raise ValueError(
                f"PCD file is larger than configured limit: {resolved.stat().st_size} > "
                f"{self.config.limits.max_pcd_bytes}"
            )
        header = read_pcd_header(resolved)
        if header.points > self.config.limits.max_pcd_points:
            raise ValueError(
                f"PCD point count is larger than configured limit: {header.points} > "
                f"{self.config.limits.max_pcd_points}"
            )
        return resolved

    def _validate_bbox(
        self,
        bbox_min: tuple[float, float, float],
        bbox_max: tuple[float, float, float],
    ) -> None:
        if len(bbox_min) != 3 or len(bbox_max) != 3:
            raise ValueError("bbox_min and bbox_max must contain exactly 3 values")
        dimensions = [float(hi) - float(lo) for lo, hi in zip(bbox_min, bbox_max, strict=True)]
        if any(value <= 0 for value in dimensions):
            raise ValueError(f"Invalid bbox dimensions: {dimensions}")
        if any(value > self.config.limits.max_bbox_edge_m for value in dimensions):
            raise ValueError(
                f"ROI edge exceeds configured limit {self.config.limits.max_bbox_edge_m} m: {dimensions}"
            )
        volume = dimensions[0] * dimensions[1] * dimensions[2]
        if volume > self.config.limits.max_bbox_volume_m3:
            raise ValueError(
                f"ROI volume exceeds configured limit {self.config.limits.max_bbox_volume_m3} m3: {volume}"
            )


def _cargo_result(
    instance: SegmentedInstance,
    recognition: RecognitionResult,
    volume: VolumeResult,
) -> CargoResult:
    return CargoResult(
        id=instance.instance_id,
        label=recognition.label,
        confidence=recognition.confidence,
        segmentation_score=instance.score,
        center=[float(v) for v in instance.box.center],
        dimensions=[float(v) for v in instance.box.dimensions],
        yaw=float(instance.box.yaw),
        obb_volume_m3=float(volume.obb_volume_m3),
        occupied_volume_m3=float(volume.occupied_volume_m3),
        occupancy_ratio=float(volume.occupancy_ratio),
        point_count=int(len(instance.points)),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--pcd", required=True)
    parser.add_argument("--bbox-min", nargs=3, type=float, required=True)
    parser.add_argument("--bbox-max", nargs=3, type=float, required=True)
    parser.add_argument("--skip-npu-load", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    pipeline = CloudMeasureEdgePipeline(config)
    output = pipeline.run(
        args.pcd,
        tuple(args.bbox_min),
        tuple(args.bbox_max),
        read_npu_load=not args.skip_npu_load,
    )
    print(json.dumps(asdict(output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
