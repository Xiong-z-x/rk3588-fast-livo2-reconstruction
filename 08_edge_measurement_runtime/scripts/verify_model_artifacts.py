#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudmeasure_edge.config import load_config


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifacts(config_path: Path, output_path: Path | None) -> dict:
    config = load_config(config_path)
    manifest_path = _resolve_manifest(config_path, config.paths.model_manifest)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", {})

    configured_paths = {
        "segmentation_rknn": config.models.segmentation_rknn,
        "voxelnet_rknn": config.models.voxelnet_rknn,
        "occupancy_checkpoint": config.models.occupancy_checkpoint,
    }
    if config.models.bev_yolo_pt is not None:
        configured_paths["bev_yolo_pretrained"] = config.models.bev_yolo_pt

    results = []
    for name, path in configured_paths.items():
        item = artifacts.get(name, {})
        artifact_path = _resolve_artifact_path(manifest_path, Path(item.get("path", path)))
        exists = artifact_path.is_file()
        results.append(
            {
                "name": name,
                "path": str(artifact_path),
                "exists": exists,
                "sizeBytes": artifact_path.stat().st_size if exists else 0,
                "sha256": sha256_file(artifact_path) if exists else "",
                "source": item.get("source_url") or item.get("source_onnx") or item.get("trainer", ""),
                "converter": item.get("converter", ""),
            }
        )

    report = {
        "config": str(config_path),
        "manifest": str(manifest_path),
        "allPresent": all(item["exists"] for item in results),
        "artifacts": results,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _resolve_manifest(config_path: Path, manifest: Path) -> Path:
    if manifest.is_absolute():
        return manifest
    return (config_path.parent.parent / manifest).resolve()


def _resolve_artifact_path(manifest_path: Path, artifact_path: Path) -> Path:
    expanded = artifact_path.expanduser()
    if expanded.is_absolute():
        return expanded
    return (manifest_path.parent.parent / expanded).resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/edge_runtime.yaml")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = verify_artifacts(Path(args.config), Path(args.output) if args.output else None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["allPresent"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
