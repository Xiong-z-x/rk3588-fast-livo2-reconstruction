#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudmeasure_edge.config import load_config
from cloudmeasure_edge.pipeline import CloudMeasureEdgePipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--pcd", required=True)
    parser.add_argument("--bbox-min", nargs=3, type=float, required=True)
    parser.add_argument("--bbox-max", nargs=3, type=float, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()

    pipeline = CloudMeasureEdgePipeline(load_config(args.config))
    runs = []
    for index in range(args.warmup + args.iterations):
        started = perf_counter()
        result = pipeline.run(
            args.pcd,
            tuple(args.bbox_min),
            tuple(args.bbox_max),
            read_npu_load=True,
        )
        elapsed_ms = (perf_counter() - started) * 1000
        if index >= args.warmup:
            runs.append({**asdict(result), "wallClockMs": round(elapsed_ms, 2)})

    total_ms = [run["timing_ms"]["totalMs"] for run in runs]
    npu_average = [
        run["npu_load"]["average"]
        for run in runs
        if run.get("npu_load") and run["npu_load"].get("average") is not None
    ]
    summary = {
        "iterations": len(runs),
        "totalMsMean": round(statistics.mean(total_ms), 2) if total_ms else 0.0,
        "totalMsP95": round(_percentile(total_ms, 95), 2) if total_ms else 0.0,
        "npuLoadMean": round(statistics.mean(npu_average), 2) if npu_average else 0.0,
        "npuLoadP95": round(_percentile(npu_average, 95), 2) if npu_average else 0.0,
    }
    report = {"summary": summary, "runs": runs}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    lo = int(index)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = index - lo
    return ordered[lo] * (1 - fraction) + ordered[hi] * fraction


if __name__ == "__main__":
    main()
