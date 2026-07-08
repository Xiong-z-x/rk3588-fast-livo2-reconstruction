from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class BoardConfig:
    host: str
    user: str
    ssh_key_path: str
    known_hosts_path: str
    strict_host_key_checking: bool
    use_sudo_for_npu_load: bool
    npu_load_path: str


@dataclass(frozen=True)
class PathConfig:
    allowed_pcd_root: Path
    model_manifest: Path


@dataclass(frozen=True)
class LimitsConfig:
    max_pcd_bytes: int
    max_pcd_points: int
    max_bbox_volume_m3: float
    max_bbox_edge_m: float


@dataclass(frozen=True)
class ModelConfig:
    segmentation_rknn: Path
    voxelnet_rknn: Path
    occupancy_checkpoint: Path
    bev_yolo_pt: Path | None


@dataclass(frozen=True)
class SegmentationConfig:
    grid_size: int
    score_threshold: float
    min_component_cells: int
    max_instances: int
    roi_feature_range_m: tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class VoxelNetConfig:
    voxel_size_m: float
    grid_shape: tuple[int, int, int]
    labels: tuple[str, ...]


@dataclass(frozen=True)
class BevYoloConfig:
    enabled: bool
    grid_size: int
    confidence_threshold: float
    max_detections: int
    min_points_per_detection: int
    class_names: tuple[str, ...]


@dataclass(frozen=True)
class OccupancyConfig:
    runtime: str
    samples_per_object: int
    occupancy_threshold: float
    batch_size: int


@dataclass(frozen=True)
class RuntimeConfig:
    board: BoardConfig
    paths: PathConfig
    limits: LimitsConfig
    models: ModelConfig
    segmentation: SegmentationConfig
    voxelnet: VoxelNetConfig
    bev_yolo: BevYoloConfig
    occupancy: OccupancyConfig


def load_config(path: str | Path) -> RuntimeConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)

    board = raw["board"]
    models = raw["models"]
    segmentation = raw["segmentation"]
    voxelnet = raw["voxelnet"]
    bev_yolo = raw.get("bev_yolo", {})
    occupancy = raw["occupancy"]
    limits = raw.get("limits", {})

    return RuntimeConfig(
        board=BoardConfig(
            host=str(board["host"]),
            user=str(board["user"]),
            ssh_key_path=str(board.get("ssh_key_path", "")),
            known_hosts_path=str(board.get("known_hosts_path", "~/.ssh/known_hosts")),
            strict_host_key_checking=bool(board.get("strict_host_key_checking", True)),
            use_sudo_for_npu_load=bool(board.get("use_sudo_for_npu_load", True)),
            npu_load_path=str(board.get("npu_load_path", "/sys/kernel/debug/rknpu/load")),
        ),
        paths=PathConfig(
            allowed_pcd_root=Path(raw.get("paths", {}).get("allowed_pcd_root", "/data/cloudmeasure/pcd")),
            model_manifest=Path(raw.get("paths", {}).get("model_manifest", "configs/model_manifest.yaml")),
        ),
        limits=LimitsConfig(
            max_pcd_bytes=int(limits.get("max_pcd_bytes", 2 * 1024 * 1024 * 1024)),
            max_pcd_points=int(limits.get("max_pcd_points", 8_000_000)),
            max_bbox_volume_m3=float(limits.get("max_bbox_volume_m3", 80.0)),
            max_bbox_edge_m=float(limits.get("max_bbox_edge_m", 12.0)),
        ),
        models=ModelConfig(
            segmentation_rknn=Path(models["segmentation_rknn"]),
            voxelnet_rknn=Path(models["voxelnet_rknn"]),
            occupancy_checkpoint=Path(models["occupancy_checkpoint"]),
            bev_yolo_pt=Path(models["bev_yolo_pt"]) if models.get("bev_yolo_pt") else None,
        ),
        segmentation=SegmentationConfig(
            grid_size=int(segmentation["grid_size"]),
            score_threshold=float(segmentation["score_threshold"]),
            min_component_cells=int(segmentation["min_component_cells"]),
            max_instances=int(segmentation["max_instances"]),
            roi_feature_range_m=tuple(float(v) for v in segmentation["roi_feature_range_m"]),
        ),
        voxelnet=VoxelNetConfig(
            voxel_size_m=float(voxelnet["voxel_size_m"]),
            grid_shape=tuple(int(v) for v in voxelnet["grid_shape"]),
            labels=tuple(str(v) for v in voxelnet["labels"]),
        ),
        bev_yolo=BevYoloConfig(
            enabled=bool(bev_yolo.get("enabled", False)),
            grid_size=int(bev_yolo.get("grid_size", 640)),
            confidence_threshold=float(bev_yolo.get("confidence_threshold", 0.25)),
            max_detections=int(bev_yolo.get("max_detections", 16)),
            min_points_per_detection=int(bev_yolo.get("min_points_per_detection", 32)),
            class_names=tuple(str(v) for v in bev_yolo.get("class_names", ("cargo_box",))),
        ),
        occupancy=OccupancyConfig(
            runtime=str(occupancy.get("runtime", "torch")),
            samples_per_object=int(occupancy["samples_per_object"]),
            occupancy_threshold=float(occupancy["occupancy_threshold"]),
            batch_size=int(occupancy["batch_size"]),
        ),
    )
