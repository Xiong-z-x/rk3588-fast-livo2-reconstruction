#!/usr/bin/env python3
"""Create a local WebGL point cloud viewer for FAST-LIVO2 result folders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


def _read_pcd(path: Path) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    with path.open("rb") as handle:
        header: List[str] = []
        while True:
            line = handle.readline()
            if not line:
                raise RuntimeError(f"PCD missing DATA line: {path}")
            text = line.decode("ascii", errors="ignore").strip()
            header.append(text)
            if text.startswith("DATA"):
                break
        meta: Dict[str, List[str]] = {}
        for line in header:
            parts = line.split()
            if len(parts) >= 2:
                meta[parts[0]] = parts[1:]
        fields = meta.get("FIELDS")
        if fields != ["x", "y", "z", "rgb"]:
            raise RuntimeError(f"Unsupported PCD fields in {path}: {fields}")
        points = int(meta["POINTS"][0])
        data = np.frombuffer(
            handle.read(points * 16),
            dtype=np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("rgb", "<u4")]),
            count=points,
        )
    xyz = np.stack([data["x"], data["y"], data["z"]], axis=1).astype(np.float32)
    rgbu = data["rgb"].astype(np.uint32)
    rgba = np.stack(
        [
            ((rgbu >> 16) & 255),
            ((rgbu >> 8) & 255),
            (rgbu & 255),
            np.full(points, 255, dtype=np.uint32),
        ],
        axis=1,
    ).astype(np.uint8)
    return xyz, rgba, {"points": points, "header": header}


def _write_bin(path: Path, xyz: np.ndarray, rgba: np.ndarray) -> None:
    dtype = np.dtype(
        [
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("r", "u1"),
            ("g", "u1"),
            ("b", "u1"),
            ("a", "u1"),
        ]
    )
    out = np.empty(len(xyz), dtype=dtype)
    out["x"] = xyz[:, 0]
    out["y"] = xyz[:, 1]
    out["z"] = xyz[:, 2]
    out["r"] = rgba[:, 0]
    out["g"] = rgba[:, 1]
    out["b"] = rgba[:, 2]
    out["a"] = rgba[:, 3]
    path.write_bytes(out.tobytes())


def _color_stats(rgba: np.ndarray) -> Dict[str, float]:
    if len(rgba) == 0:
        return {}
    rgb = rgba[:, :3].astype(np.float32) / 255.0
    mx = rgb.max(axis=1)
    mn = rgb.min(axis=1)
    sat = np.where(mx <= 1e-6, 0.0, (mx - mn) / mx)
    return {
        "satMean": float(np.mean(sat)),
        "satP50": float(np.percentile(sat, 50)),
        "satP90": float(np.percentile(sat, 90)),
        "lowSatPct": float(np.mean(sat < 0.10) * 100.0),
        "valueMean": float(np.mean(mx)),
    }


def _dataset_specs(result_dir: Path) -> List[Dict[str, Any]]:
    return [
        {
            "id": "fast_livo2_color",
            "name": "FAST-LIVO2 彩色成品 all_raw_points",
            "source": result_dir / "all_raw_points.pcd",
            "file": "fast_livo2_color.bin",
            "defaultVisible": True,
            "pointSize": 2.0,
            "alpha": 1.0,
            "description": "FAST-LIVO2 输出的最终彩色 PCD，未使用 all_downsampled_points。",
        },
        {
            "id": "livox_raw_stride10",
            "name": "/livox/lidar 原始累计 stride10",
            "source": result_dir / "livox_lidar_raw_accum_view_stride10.pcd",
            "file": "livox_lidar_raw_stride10.bin",
            "defaultVisible": False,
            "pointSize": 1.5,
            "alpha": 0.85,
            "description": "不经过 FAST-LIVO2 位姿补偿，直接累计原始雷达点；每 10 点取 1 点用于快速观察。",
        },
        {
            "id": "lidar_pose_mapped_height",
            "name": "LiDAR-only 位姿建图高度着色 stride10",
            "source": result_dir / "lidar_pose_mapped_height_view_stride10.pcd",
            "file": "lidar_pose_mapped_height_stride10.bin",
            "defaultVisible": True,
            "pointSize": 1.5,
            "alpha": 0.95,
            "description": "使用 FAST-LIVO2 lidar_poses.txt 将 /livox/lidar 转到世界系，按高度着色，不使用相机 RGB。",
        },
        {
            "id": "lidar_pose_mapped_height_full",
            "name": "LiDAR-only 位姿建图高度着色 full",
            "source": result_dir / "lidar_pose_mapped_height_full.pcd",
            "file": "lidar_pose_mapped_height_full.bin",
            "defaultVisible": False,
            "pointSize": 1.0,
            "alpha": 0.85,
            "description": "完整 LiDAR-only 位姿建图点云，点数较多，打开时浏览器会占用更多显存。",
        },
        {
            "id": "trajectory",
            "name": "FAST-LIVO2 LiDAR 位姿轨迹",
            "source": result_dir / "lidar_pose_trajectory_points.pcd",
            "file": "lidar_pose_trajectory_points.bin",
            "defaultVisible": True,
            "pointSize": 5.0,
            "alpha": 1.0,
            "description": "由 lidar_poses.txt 生成的红色轨迹点，用于观察运动路径和跳变。",
        },
        {
            "id": "livox_raw_full",
            "name": "/livox/lidar 原始累计 full",
            "source": result_dir / "livox_lidar_raw_accum_full.pcd",
            "file": "livox_lidar_raw_full.bin",
            "defaultVisible": False,
            "pointSize": 1.0,
            "alpha": 0.70,
            "description": "完整原始雷达累计点云，不经过 FAST-LIVO2 建图、位姿补偿或相机上色。",
        },
    ]


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FAST-LIVO2 / Livox 点云 WebGL 查看器</title>
  <style>
    :root { color-scheme: light; --bg:#f6f8fb; --panel:rgba(255,255,255,.94); --line:#d7dee8; --text:#142033; --muted:#627085; --accent:#0477bf; }
    * { box-sizing: border-box; }
    html, body { margin:0; width:100%; height:100%; overflow:hidden; background:var(--bg); color:var(--text); font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    canvas { width:100vw; height:100vh; display:block; background:#fff; cursor:grab; }
    canvas:active { cursor:grabbing; }
    .panel { position:fixed; left:16px; top:16px; width:430px; max-height:calc(100vh - 32px); overflow:auto; padding:14px 16px; background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 10px 30px rgba(20,32,51,.12); backdrop-filter:blur(8px); }
    h1 { margin:0 0 6px; font-size:18px; line-height:1.2; }
    .sub { color:var(--muted); font-size:12px; line-height:1.5; margin-bottom:12px; }
    .row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 0; border-top:1px solid #edf1f6; }
    .row:first-of-type { border-top:0; }
    .row label { display:flex; align-items:flex-start; gap:8px; font-size:13px; font-weight:650; }
    .row small { display:block; color:var(--muted); font-weight:400; margin-top:3px; line-height:1.35; }
    input[type=range] { width:115px; accent-color:var(--accent); }
    input[type=checkbox] { width:16px; height:16px; accent-color:var(--accent); margin-top:2px; }
    button { border:1px solid var(--line); background:#fff; color:var(--text); padding:7px 10px; border-radius:7px; font-weight:650; cursor:pointer; }
    button:hover { border-color:#9db5cc; }
    .stats { margin-top:12px; padding-top:12px; border-top:1px solid #edf1f6; color:var(--muted); font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace; font-size:12px; line-height:1.55; white-space:pre-wrap; }
    .badge { display:inline-flex; align-items:center; gap:6px; padding:3px 7px; border-radius:999px; background:#eef7ff; color:#075985; font-size:12px; font-weight:700; }
    .legend { position:fixed; right:16px; bottom:16px; color:var(--muted); background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 12px; font-size:12px; line-height:1.6; }
  </style>
</head>
<body>
  <canvas id="gl"></canvas>
  <section class="panel">
    <h1>本机 GPU 点云查看器</h1>
    <div class="sub">
      <span class="badge" id="titleBadge">FAST-LIVO2</span><br />
      每个图层按需加载。建议先看 FAST-LIVO2 彩色成品、LiDAR-only stride10 和红色轨迹；full 图层点数很大，打开时会占用更多显存。
    </div>
    <div id="layers"></div>
    <div class="row"><label>全局点大小</label><input id="globalPointSize" type="range" min="0.5" max="5" step="0.1" value="1" /></div>
    <div class="row"><label>背景亮度</label><input id="bg" type="range" min="0" max="255" step="1" value="255" /></div>
    <div class="row"><button id="reset">重置视角</button><button id="top">俯视</button><button id="front">正视</button></div>
    <div class="stats" id="stats">正在加载 manifest...</div>
  </section>
  <div class="legend">鼠标左键旋转 · 右键/Shift 平移 · 滚轮缩放<br />图层 full 较大，按需打开。</div>
  <script>
    const canvas = document.getElementById("gl");
    const gl = canvas.getContext("webgl", { antialias: true, alpha: false });
    if (!gl) throw new Error("WebGL 不可用");
    const vs = `
      attribute vec3 aPosition; attribute vec4 aColor;
      uniform mat4 uMvp; uniform float uPointSize; uniform float uAlpha;
      varying vec4 vColor;
      void main(){ gl_Position = uMvp * vec4(aPosition,1.0); gl_PointSize = uPointSize; vColor = vec4(aColor.rgb, aColor.a * uAlpha); }
    `;
    const fs = `precision mediump float; varying vec4 vColor; void main(){ gl_FragColor = vColor; }`;
    function shader(type, src){ const s=gl.createShader(type); gl.shaderSource(s,src); gl.compileShader(s); if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
    const program=gl.createProgram(); gl.attachShader(program,shader(gl.VERTEX_SHADER,vs)); gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs)); gl.linkProgram(program); gl.useProgram(program);
    const loc={ pos:gl.getAttribLocation(program,"aPosition"), col:gl.getAttribLocation(program,"aColor"), mvp:gl.getUniformLocation(program,"uMvp"), point:gl.getUniformLocation(program,"uPointSize"), alpha:gl.getUniformLocation(program,"uAlpha") };
    gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    let manifest=null, layers=[], yaw=-0.75, pitch=-0.75, dist=9, pan=[0,0,0], dragging=false, last=[0,0], mode="rotate";
    function matMul(a,b){ const o=new Float32Array(16); for(let r=0;r<4;r++)for(let c=0;c<4;c++)o[c*4+r]=a[0*4+r]*b[c*4+0]+a[1*4+r]*b[c*4+1]+a[2*4+r]*b[c*4+2]+a[3*4+r]*b[c*4+3]; return o; }
    function perspective(fovy,aspect,near,far){ const f=1/Math.tan(fovy/2), nf=1/(near-far); return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]); }
    function translate(x,y,z){ return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,x,y,z,1]); }
    function rotX(a){ const c=Math.cos(a),s=Math.sin(a); return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]); }
    function rotZ(a){ const c=Math.cos(a),s=Math.sin(a); return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]); }
    function resize(){ const dpr=Math.min(devicePixelRatio||1,2); const w=Math.floor(innerWidth*dpr), h=Math.floor(innerHeight*dpr); if(canvas.width!==w||canvas.height!==h){ canvas.width=w; canvas.height=h; gl.viewport(0,0,w,h); } }
    function resetView(){ const span=Math.max(...manifest.globalSpan); dist=span*1.8+1; yaw=-0.75; pitch=-0.75; pan=[-manifest.globalCenter[0],-manifest.globalCenter[1],-manifest.globalCenter[2]]; }
    function mvp(){ const aspect=canvas.width/canvas.height; let m=perspective(Math.PI/4,aspect,0.01,10000); let v=translate(0,0,-dist); v=matMul(v,rotX(pitch)); v=matMul(v,rotZ(yaw)); v=matMul(v,translate(pan[0],pan[1],pan[2])); return matMul(m,v); }
    async function loadLayer(layer){ if(layer.loaded||layer.loading) return; layer.loading=true; updateStats(); const res=await fetch("data/"+layer.file); const buf=await res.arrayBuffer(); const stride=manifest.strideBytes; const count=buf.byteLength/stride; const vbuf=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,vbuf); gl.bufferData(gl.ARRAY_BUFFER,buf,gl.STATIC_DRAW); layer.buffer=vbuf; layer.count=count; layer.loaded=true; layer.loading=false; updateStats(); }
    function draw(){ resize(); const bg=Number(document.getElementById("bg").value)/255; gl.clearColor(bg,bg,bg,1); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT); if(manifest){ const matrix=mvp(); const globalScale=Number(document.getElementById("globalPointSize").value); for(const l of layers){ if(!l.visible) continue; if(!l.loaded){ loadLayer(l); continue; } gl.bindBuffer(gl.ARRAY_BUFFER,l.buffer); gl.enableVertexAttribArray(loc.pos); gl.vertexAttribPointer(loc.pos,3,gl.FLOAT,false,16,0); gl.enableVertexAttribArray(loc.col); gl.vertexAttribPointer(loc.col,4,gl.UNSIGNED_BYTE,true,16,12); gl.uniformMatrix4fv(loc.mvp,false,matrix); gl.uniform1f(loc.point,l.pointSize*globalScale); gl.uniform1f(loc.alpha,l.alpha); gl.drawArrays(gl.POINTS,0,l.count); } } requestAnimationFrame(draw); }
    function updateStats(){ if(!manifest) return; const lines=[]; lines.push(`数据集: ${manifest.title || ""}`); lines.push(`全局范围: ${manifest.globalSpan.map(v=>v.toFixed(2)).join(" x ")} m`); for(const l of layers){ lines.push(`${l.visible?"[显示]":"[隐藏]"} ${l.name}: ${l.points.toLocaleString()} 点 ${l.loaded?"已加载":l.loading?"加载中":"未加载"}`); } document.getElementById("stats").textContent=lines.join("\n"); }
    function setupUi(){ document.getElementById("titleBadge").textContent=manifest.title||"FAST-LIVO2"; const root=document.getElementById("layers"); root.innerHTML=""; for(const l of layers){ const row=document.createElement("div"); row.className="row"; const label=document.createElement("label"); const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=l.visible; cb.onchange=()=>{l.visible=cb.checked; updateStats();}; const text=document.createElement("span"); text.innerHTML=`${l.name}<small>${l.description}<br />${l.points.toLocaleString()} 点</small>`; label.append(cb,text); const range=document.createElement("input"); range.type="range"; range.min="0.5"; range.max="6"; range.step="0.1"; range.value=l.pointSize; range.oninput=()=>{l.pointSize=Number(range.value);}; row.append(label,range); root.append(row); } document.getElementById("reset").onclick=resetView; document.getElementById("top").onclick=()=>{yaw=0; pitch=0;}; document.getElementById("front").onclick=()=>{yaw=-Math.PI/2; pitch=-Math.PI/2.8;}; updateStats(); }
    canvas.addEventListener("mousedown",e=>{dragging=true; last=[e.clientX,e.clientY]; mode=(e.button===2||e.shiftKey)?"pan":"rotate";});
    addEventListener("mouseup",()=>dragging=false); canvas.addEventListener("contextmenu",e=>e.preventDefault());
    addEventListener("mousemove",e=>{ if(!dragging) return; const dx=e.clientX-last[0], dy=e.clientY-last[1]; last=[e.clientX,e.clientY]; if(mode==="rotate"){ yaw+=dx*0.006; pitch+=dy*0.006; pitch=Math.max(-Math.PI/2,Math.min(Math.PI/2,pitch)); } else { const s=dist*0.0015; pan[0]+=dx*s; pan[1]-=dy*s; } });
    canvas.addEventListener("wheel",e=>{ e.preventDefault(); dist*=Math.exp(e.deltaY*0.001); dist=Math.max(0.05,dist); }, {passive:false});
    fetch("data/manifest.json").then(r=>r.json()).then(m=>{ manifest=m; layers=m.datasets.map(d=>({...d,visible:!!d.defaultVisible,loaded:false,loading:false,buffer:null,count:0})); resetView(); setupUi(); });
    draw();
  </script>
</body>
</html>
"""


def create_viewer(result_dir: Path, title: str) -> None:
    viewer_dir = result_dir / "webgl_viewer"
    data_dir = viewer_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {"title": title, "strideBytes": 16, "datasets": []}
    global_min = np.array([np.inf, np.inf, np.inf], dtype=np.float64)
    global_max = np.array([-np.inf, -np.inf, -np.inf], dtype=np.float64)

    for spec in _dataset_specs(result_dir):
        source = spec["source"]
        if not source.exists():
            raise FileNotFoundError(source)
        xyz, rgba, _meta = _read_pcd(source)
        bbox_min = xyz.min(axis=0).astype(float)
        bbox_max = xyz.max(axis=0).astype(float)
        global_min = np.minimum(global_min, bbox_min)
        global_max = np.maximum(global_max, bbox_max)
        out_file = data_dir / spec["file"]
        _write_bin(out_file, xyz, rgba)
        item = {k: v for k, v in spec.items() if k != "source"}
        item.update(
            {
                "points": int(len(xyz)),
                "bytes": int(out_file.stat().st_size),
                "bboxMin": bbox_min.tolist(),
                "bboxMax": bbox_max.tolist(),
                "sourcePcd": source.name,
                "colorStats": _color_stats(rgba),
            }
        )
        manifest["datasets"].append(item)
        print(f"[OK] {title} {item['id']} points={item['points']} bytes={item['bytes']}")

    manifest["globalBboxMin"] = global_min.tolist()
    manifest["globalBboxMax"] = global_max.tolist()
    manifest["globalCenter"] = ((global_min + global_max) * 0.5).tolist()
    manifest["globalSpan"] = (global_max - global_min).tolist()
    (data_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (viewer_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    print(f"[OK] viewer={viewer_dir / 'index.html'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    create_viewer(args.result_dir, args.title)


if __name__ == "__main__":
    main()
