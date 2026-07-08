from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import load_config
from .pipeline import CloudMeasureEdgePipeline


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "edge_runtime.yaml"

app = FastAPI(title="CloudMeasure Edge AI Runtime", version="1.0.0")


class SegmentRecognizeVolumeRequest(BaseModel):
    pcd_path: str = Field(..., alias="pcdPath")
    bbox_min: tuple[float, float, float] = Field(..., alias="bboxMin")
    bbox_max: tuple[float, float, float] = Field(..., alias="bboxMax")
    read_npu_load: bool = Field(default=True, alias="readNpuLoad")


@lru_cache(maxsize=1)
def get_pipeline() -> CloudMeasureEdgePipeline:
    return CloudMeasureEdgePipeline(load_config(DEFAULT_CONFIG))


@app.get("/api/edge-ai/health")
def health() -> dict:
    return {
        "status": "ok",
        "config": str(DEFAULT_CONFIG),
    }


@app.post("/api/edge-ai/segment-recognize-volume")
def segment_recognize_volume(request: SegmentRecognizeVolumeRequest) -> dict:
    try:
        output = get_pipeline().run(
            request.pcd_path,
            request.bbox_min,
            request.bbox_max,
            read_npu_load=request.read_npu_load,
        )
        return asdict(output)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
