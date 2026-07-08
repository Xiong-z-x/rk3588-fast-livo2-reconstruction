#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType


def _load_base(path: Path) -> ModuleType:
    source = path.read_text(encoding="utf-8")
    if "wrapAngle" not in source:
        raise RuntimeError("Base viewer does not support unlimited yaw/pitch rotation")
    if 'powerPreference: "high-performance"' not in source:
        raise RuntimeError("Base viewer does not request the high-performance GPU")
    spec = importlib.util.spec_from_file_location("pcd_direct_viewer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load viewer module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--base-script",
        type=Path,
        default=Path("/root/fast_livo2_runs/create_pcd_direct_webgl_viewer.py"),
    )
    args = parser.parse_args()

    base = _load_base(args.base_script)
    base.DATASETS = [dataset for dataset in base.DATASETS if dataset["id"] != "fast_livo2_color"]
    viewer_dir = base.create_viewer(args.result_dir, args.title)

    manifest_path = viewer_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(dataset["id"] == "fast_livo2_color" for dataset in manifest["datasets"]):
        raise RuntimeError("Color layer unexpectedly remained in LiDAR-only manifest")
    manifest["notes"] = (
        "纯 LiDAR+IMU：默认加载位姿累计高度着色 full 点云和红色轨迹；"
        "stride10 仅用于轻量预览。WebGL 请求高性能 GPU，旋转不限制俯仰角。"
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = viewer_dir / "index.html"
    html = index_path.read_text(encoding="utf-8")
    html = re.sub(r"<title>.*?</title>", f"<title>{args.title}</title>", html, count=1, flags=re.S)
    html = re.sub(r"<h1>.*?</h1>", "<h1>LiDAR-only 三维点云查看器</h1>", html, count=1, flags=re.S)
    html = re.sub(
        r'<div class="sub">.*?</div>',
        '<div class="sub"><span class="badge" id="titleBadge">ONLY_LIO</span><br />'
        "FAST-LIVO2 ONLY_LIO 位姿累计结果，不包含相机图像或 RGB 上色。"
        "full 图层默认保留完整点数，stride10 仅作为额外预览。</div>",
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'<div class="legend">.*?</div>',
        '<div class="legend">左键：无限旋转｜滚轮：缩放｜中键：平移｜'
        "右键上下拖动：缩放｜Shift+左键：平移<br />"
        "大点云首次载入需要等待；GPU 信息显示在左侧状态区。</div>",
        html,
        count=1,
        flags=re.S,
    )
    index_path.write_text(html, encoding="utf-8")
    print(f"[OK] lidar_only_viewer={index_path}")


if __name__ == "__main__":
    main()
