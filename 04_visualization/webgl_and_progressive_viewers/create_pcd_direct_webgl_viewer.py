#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import numpy as np


PCD_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("rgb", "<u4")])


DATASETS: list[dict[str, Any]] = [
    {
        "id": "fast_livo2_color",
        "name": "FAST-LIVO2 彩色三维重建 all_raw_points",
        "file": "../all_raw_points.pcd",
        "pcd": "all_raw_points.pcd",
        "defaultVisible": True,
        "pointSize": 1.6,
        "alpha": 1.0,
        "description": "FAST-LIVO2 最终彩色 PCD，使用相机 RGB 上色；这是彩色建模成品。",
    },
    {
        "id": "lidar_pose_mapped_height_full",
        "name": "LiDAR-only 位姿累计高度着色 full",
        "file": "../lidar_pose_mapped_height_full.pcd",
        "pcd": "lidar_pose_mapped_height_full.pcd",
        "defaultVisible": True,
        "pointSize": 0.9,
        "alpha": 0.92,
        "description": "使用 FAST-LIVO2 位姿把原始雷达点累计到世界系，按高度伪彩色；不使用相机 RGB。",
    },
    {
        "id": "trajectory",
        "name": "FAST-LIVO2 LiDAR 位姿轨迹",
        "file": "../lidar_pose_trajectory_points.pcd",
        "pcd": "lidar_pose_trajectory_points.pcd",
        "defaultVisible": True,
        "pointSize": 5.0,
        "alpha": 1.0,
        "description": "由 lidar_poses.txt 生成的红色轨迹点，用于检查运动路径和跳变。",
    },
    {
        "id": "lidar_pose_mapped_height_stride10",
        "name": "LiDAR-only 位姿累计高度着色 stride10",
        "file": "../lidar_pose_mapped_height_view_stride10.pcd",
        "pcd": "lidar_pose_mapped_height_view_stride10.pcd",
        "defaultVisible": False,
        "pointSize": 1.4,
        "alpha": 0.96,
        "description": "LiDAR-only 的轻量预览层，每 10 点取 1 点，适合快速观察。",
    },
    {
        "id": "livox_raw_stride10",
        "name": "/livox/lidar 原始累计 stride10",
        "file": "../livox_lidar_raw_accum_view_stride10.pcd",
        "pcd": "livox_lidar_raw_accum_view_stride10.pcd",
        "defaultVisible": False,
        "pointSize": 1.3,
        "alpha": 0.85,
        "description": "不经过位姿补偿，直接叠加原始雷达点；用于检查原始数据覆盖。",
    },
    {
        "id": "livox_raw_full",
        "name": "/livox/lidar 原始累计 full",
        "file": "../livox_lidar_raw_accum_full.pcd",
        "pcd": "livox_lidar_raw_accum_full.pcd",
        "defaultVisible": False,
        "pointSize": 0.8,
        "alpha": 0.70,
        "description": "完整原始雷达累计，不经过 FAST-LIVO2 位姿补偿或相机上色；点数很大，按需打开。",
    },
]


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FAST-LIVO2 大场景点云 WebGL 查看器</title>
  <style>
    :root { color-scheme: light; --bg:#f6f8fb; --panel:rgba(255,255,255,.95); --line:#d7dee8; --text:#142033; --muted:#627085; --accent:#0477bf; --warn:#a16207; }
    * { box-sizing:border-box; }
    html,body { margin:0; width:100%; height:100%; overflow:hidden; background:var(--bg); color:var(--text); font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    canvas { width:100vw; height:100vh; display:block; background:#fff; cursor:grab; }
    canvas:active { cursor:grabbing; }
    .panel { position:fixed; left:16px; top:16px; width:480px; max-height:calc(100vh - 32px); overflow:auto; padding:14px 16px; background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 10px 30px rgba(20,32,51,.13); backdrop-filter:blur(8px); }
    h1 { margin:0 0 6px; font-size:18px; line-height:1.2; }
    .sub { color:var(--muted); font-size:12px; line-height:1.5; margin-bottom:12px; }
    .badge { display:inline-flex; padding:3px 7px; border-radius:999px; background:#eef7ff; color:#075985; font-size:12px; font-weight:700; margin-bottom:6px; }
    .row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 0; border-top:1px solid #edf1f6; }
    .row:first-of-type { border-top:0; }
    .row label { display:flex; align-items:flex-start; gap:8px; font-size:13px; font-weight:650; }
    .row small { display:block; color:var(--muted); font-weight:400; margin-top:3px; line-height:1.35; }
    input[type=checkbox] { width:16px; height:16px; accent-color:var(--accent); margin-top:2px; flex:0 0 auto; }
    input[type=range] { width:115px; accent-color:var(--accent); }
    button { border:1px solid var(--line); background:#fff; color:var(--text); padding:7px 10px; border-radius:7px; font-weight:650; cursor:pointer; }
    button:hover { border-color:#9db5cc; }
    .stats { margin-top:12px; padding-top:12px; border-top:1px solid #edf1f6; color:var(--muted); font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace; font-size:12px; line-height:1.55; white-space:pre-wrap; }
    .warn { color:var(--warn); }
    .legend { position:fixed; right:16px; bottom:16px; color:var(--muted); background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px 12px; font-size:12px; line-height:1.6; }
  </style>
</head>
<body>
  <canvas id="gl"></canvas>
  <section class="panel">
    <h1>本机 GPU 大场景点云查看器</h1>
    <div class="sub">
      <span class="badge" id="titleBadge">FAST-LIVO2</span><br />
      默认加载 FAST-LIVO2 彩色成品、LiDAR-only full 和红色轨迹。full 图层较大，首次加载需要等待。
    </div>
    <div id="layers"></div>
    <div class="row"><label>全局点大小</label><input id="globalPointSize" type="range" min="0.4" max="4" step="0.1" value="1" /></div>
    <div class="row"><label>背景亮度</label><input id="bg" type="range" min="0" max="255" step="1" value="255" /></div>
    <div class="row"><button id="reset">重置视角</button><button id="top">俯视</button><button id="front">正视</button></div>
    <div class="stats" id="stats">正在加载 manifest...</div>
  </section>
  <div class="legend">RViz 风格：左键旋转 | 滚轮缩放 | 按住滚轮平移 | 右键上下拖动缩放 | Shift+左键平移<br />若浏览器卡顿，先关闭 raw full，只保留 LiDAR-only full。</div>
  <script>
    const canvas = document.getElementById("gl");
    const gl = canvas.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "high-performance", desynchronized: true, preserveDrawingBuffer: false })
      || canvas.getContext("webgl", { antialias: false, alpha: false, powerPreference: "high-performance", desynchronized: true, preserveDrawingBuffer: false });
    if (!gl) throw new Error("WebGL 不可用");
    const vs = `
      attribute vec3 aPosition; attribute vec4 aColorBgra;
      uniform mat4 uMvp; uniform float uPointSize; uniform float uAlpha;
      varying vec4 vColor;
      void main(){
        gl_Position = uMvp * vec4(aPosition,1.0);
        gl_PointSize = uPointSize;
        vColor = vec4(aColorBgra.b, aColorBgra.g, aColorBgra.r, uAlpha);
      }
    `;
    const fs = `precision mediump float; varying vec4 vColor; void main(){ gl_FragColor = vColor; }`;
    function shader(type, src){ const s=gl.createShader(type); gl.shaderSource(s,src); gl.compileShader(s); if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
    const program=gl.createProgram(); gl.attachShader(program,shader(gl.VERTEX_SHADER,vs)); gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs)); gl.linkProgram(program); gl.useProgram(program);
    const loc={ pos:gl.getAttribLocation(program,"aPosition"), col:gl.getAttribLocation(program,"aColorBgra"), mvp:gl.getUniformLocation(program,"uMvp"), point:gl.getUniformLocation(program,"uPointSize"), alpha:gl.getUniformLocation(program,"uAlpha") };
    gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    const dbgInfo = gl.getExtension("WEBGL_debug_renderer_info");
    const gpuRenderer = dbgInfo ? gl.getParameter(dbgInfo.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    let manifest=null, layers=[], yaw=-0.75, pitch=-0.75, dist=12, pan=[0,0,0], dragging=false, last=[0,0], mode="rotate";
    let loadingCount=0, renderPending=false;
    function requestRender(){ if(renderPending) return; renderPending=true; requestAnimationFrame(()=>{ renderPending=false; draw(); }); }
    function matMul(a,b){ const o=new Float32Array(16); for(let r=0;r<4;r++)for(let c=0;c<4;c++)o[c*4+r]=a[0*4+r]*b[c*4+0]+a[1*4+r]*b[c*4+1]+a[2*4+r]*b[c*4+2]+a[3*4+r]*b[c*4+3]; return o; }
    function perspective(fovy,aspect,near,far){ const f=1/Math.tan(fovy/2), nf=1/(near-far); return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]); }
    function translate(x,y,z){ return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,x,y,z,1]); }
    function rotX(a){ const c=Math.cos(a),s=Math.sin(a); return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]); }
    function rotZ(a){ const c=Math.cos(a),s=Math.sin(a); return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]); }
    function resize(){ const dpr=Math.min(devicePixelRatio||1,2); const w=Math.floor(innerWidth*dpr), h=Math.floor(innerHeight*dpr); if(canvas.width!==w||canvas.height!==h){ canvas.width=w; canvas.height=h; gl.viewport(0,0,w,h); } }
    function resetView(){ const span=Math.max(...manifest.globalSpan); dist=span*1.65+1; yaw=-0.75; pitch=-0.75; pan=[-manifest.globalCenter[0],-manifest.globalCenter[1],-manifest.globalCenter[2]]; }
    function mvp(){ const aspect=canvas.width/canvas.height; let m=perspective(Math.PI/4,aspect,0.01,10000); let v=translate(0,0,-dist); v=matMul(v,rotX(pitch)); v=matMul(v,rotZ(yaw)); v=matMul(v,translate(pan[0],pan[1],pan[2])); return matMul(m,v); }
    function pcdDataOffset(buffer){
      const bytes = new Uint8Array(buffer);
      const needle = new TextEncoder().encode("DATA binary");
      for(let i=0;i<Math.min(bytes.length,4096)-needle.length;i++){
        let ok=true; for(let j=0;j<needle.length;j++){ if(bytes[i+j]!==needle[j]){ ok=false; break; } }
        if(ok){ while(i<bytes.length && bytes[i]!==10) i++; return i+1; }
      }
      throw new Error("PCD header missing DATA binary");
    }
    async function loadLayer(layer){
      if(layer.loaded||layer.loading||loadingCount>=1) return;
      loadingCount++; layer.loading=true; updateStats(); requestRender();
      try {
        const res=await fetch(layer.file);
        if(!res.ok) throw new Error(`加载失败 ${layer.file}: ${res.status}`);
        const buffer=await res.arrayBuffer();
        const offset=pcdDataOffset(buffer);
        const dataView=new Uint8Array(buffer, offset);
        const vbuf=gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER,vbuf);
        gl.bufferData(gl.ARRAY_BUFFER,dataView,gl.STATIC_DRAW);
        layer.buffer=vbuf;
        layer.count=dataView.byteLength/16;
        layer.loaded=true;
      } finally {
        layer.loading=false; loadingCount--; updateStats(); requestRender();
      }
    }
    function draw(){
      resize(); const bg=Number(document.getElementById("bg").value)/255; gl.clearColor(bg,bg,bg,1); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      if(manifest){ const matrix=mvp(); const globalScale=Number(document.getElementById("globalPointSize").value);
        for(const l of layers){ if(!l.visible) continue; if(!l.loaded){ loadLayer(l); continue; }
          gl.bindBuffer(gl.ARRAY_BUFFER,l.buffer);
          gl.enableVertexAttribArray(loc.pos); gl.vertexAttribPointer(loc.pos,3,gl.FLOAT,false,16,0);
          gl.enableVertexAttribArray(loc.col); gl.vertexAttribPointer(loc.col,4,gl.UNSIGNED_BYTE,true,16,12);
          gl.uniformMatrix4fv(loc.mvp,false,matrix); gl.uniform1f(loc.point,l.pointSize*globalScale); gl.uniform1f(loc.alpha,l.alpha);
          gl.drawArrays(gl.POINTS,0,l.count);
        }
      }
    }
    function updateStats(){
      if(!manifest) return;
      const lines=[]; lines.push(`数据集: ${manifest.title || ""}`); lines.push(`GPU: ${gpuRenderer}`); lines.push(`全局范围: ${manifest.globalSpan.map(v=>v.toFixed(2)).join(" x ")} m`);
      if(manifest.notes) lines.push(`提示: ${manifest.notes}`);
      for(const l of layers){ lines.push(`${l.visible?"[显示]":"[隐藏]"} ${l.name}: ${l.points.toLocaleString()} 点 ${l.loaded?"已加载":l.loading?"加载中":"未加载"}`); }
      document.getElementById("stats").textContent=lines.join("\\n");
    }
    function setupUi(){
      document.getElementById("titleBadge").textContent=manifest.title||"FAST-LIVO2";
      const root=document.getElementById("layers"); root.innerHTML="";
      for(const l of layers){
        const row=document.createElement("div"); row.className="row";
        const label=document.createElement("label"); const cb=document.createElement("input"); cb.type="checkbox"; cb.checked=l.visible;
        cb.onchange=()=>{l.visible=cb.checked; updateStats(); requestRender();};
        const text=document.createElement("span"); text.innerHTML=`${l.name}<small>${l.description}<br />${l.points.toLocaleString()} 点，${(l.bytes/1048576).toFixed(1)} MB</small>`;
        label.append(cb,text);
        const range=document.createElement("input"); range.type="range"; range.min="0.4"; range.max="6"; range.step="0.1"; range.value=l.pointSize; range.oninput=()=>{l.pointSize=Number(range.value); requestRender();};
        row.append(label,range); root.append(row);
      }
      document.getElementById("reset").onclick=()=>{resetView(); requestRender();}; document.getElementById("top").onclick=()=>{yaw=0; pitch=0; requestRender();}; document.getElementById("front").onclick=()=>{yaw=-Math.PI/2; pitch=-Math.PI/2.8; requestRender();};
      updateStats();
    }
    canvas.addEventListener("mousedown",e=>{
      e.preventDefault();
      dragging=true; last=[e.clientX,e.clientY];
      mode=(e.button===1 || (e.button===0 && e.shiftKey)) ? "pan" : (e.button===2 ? "zoom" : "rotate");
    });
    addEventListener("mouseup",()=>dragging=false); canvas.addEventListener("contextmenu",e=>e.preventDefault());
    function wrapAngle(a){ const tau=Math.PI*2; return ((a+Math.PI)%tau+tau)%tau-Math.PI; }
    addEventListener("mousemove",e=>{ if(!dragging) return; const dx=e.clientX-last[0], dy=e.clientY-last[1]; last=[e.clientX,e.clientY]; if(mode==="rotate"){ yaw=wrapAngle(yaw+dx*0.006); pitch=wrapAngle(pitch+dy*0.006); } else if(mode==="pan"){ const s=dist*0.0015; pan[0]+=dx*s; pan[1]-=dy*s; } else { dist*=Math.exp(dy*0.01); dist=Math.max(0.05,dist); } requestRender(); });
    canvas.addEventListener("wheel",e=>{ e.preventDefault(); dist*=Math.exp(e.deltaY*0.001); dist=Math.max(0.05,dist); requestRender(); }, {passive:false});
    addEventListener("resize",requestRender);
    fetch("manifest.json").then(r=>r.json()).then(m=>{ manifest=m; layers=m.datasets.map(d=>({...d,visible:!!d.defaultVisible,loaded:false,loading:false,buffer:null,count:0})); resetView(); setupUi(); requestRender(); });
  </script>
</body>
</html>
"""


def _read_pcd_header(path: Path) -> dict[str, Any]:
    header: dict[str, str] = {}
    with path.open("rb") as handle:
        while True:
            raw = handle.readline()
            if not raw:
                raise RuntimeError(f"PCD missing DATA line: {path}")
            line = raw.decode("ascii", errors="replace").strip()
            if line and not line.startswith("#"):
                key, *rest = line.split(maxsplit=1)
                header[key.upper()] = rest[0] if rest else ""
            if line.startswith("DATA"):
                break
    fields = header.get("FIELDS", "")
    if fields != "x y z rgb":
        raise RuntimeError(f"Unsupported PCD fields in {path}: {fields}")
    return {
        "points": int(header["POINTS"]),
        "width": int(header["WIDTH"]),
        "height": int(header["HEIGHT"]),
        "data": header["DATA"],
    }


def _read_stats(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _bbox_from_stats(stats: dict[str, str]) -> list[float] | None:
    value = stats.get("bbox_xyz")
    if not value:
        return None
    parsed = ast.literal_eval(value)
    if isinstance(parsed, list) and len(parsed) == 6:
        return [float(x) for x in parsed]
    return None


def _bbox_from_pcd(path: Path) -> list[float]:
    with path.open("rb") as handle:
        while True:
            raw = handle.readline()
            if not raw:
                raise RuntimeError(f"PCD missing DATA line: {path}")
            if raw.startswith(b"POINTS"):
                points = int(raw.decode("ascii").split()[1])
            if raw.startswith(b"DATA"):
                break
        data = np.frombuffer(handle.read(points * 16), dtype=PCD_DTYPE, count=points)
    xyz = np.stack([data["x"], data["y"], data["z"]], axis=1)
    mins = xyz.min(axis=0)
    maxs = xyz.max(axis=0)
    return [float(mins[0]), float(mins[1]), float(mins[2]), float(maxs[0]), float(maxs[1]), float(maxs[2])]


def _dataset_bbox(result_dir: Path, dataset_id: str, pcd_path: Path) -> list[float]:
    raw_stats = _read_stats(result_dir / "livox_lidar_raw_accum_stats.txt")
    mapped_stats = _read_stats(result_dir / "lidar_pose_mapped_height_stats.txt")
    if dataset_id.startswith("livox_raw"):
        bbox = _bbox_from_stats(raw_stats)
        if bbox:
            return bbox
    if dataset_id.startswith("lidar_pose_mapped") or dataset_id == "trajectory":
        bbox = _bbox_from_stats(mapped_stats)
        if bbox:
            return bbox
    return _bbox_from_pcd(pcd_path)


def create_viewer(result_dir: Path, title: str) -> Path:
    viewer_dir = result_dir / "webgl_viewer"
    viewer_dir.mkdir(parents=True, exist_ok=True)
    datasets: list[dict[str, Any]] = []
    global_min = np.array([np.inf, np.inf, np.inf], dtype=np.float64)
    global_max = np.array([-np.inf, -np.inf, -np.inf], dtype=np.float64)

    for spec in DATASETS:
        pcd_path = result_dir / spec["pcd"]
        if not pcd_path.exists():
            raise FileNotFoundError(pcd_path)
        header = _read_pcd_header(pcd_path)
        bbox = _dataset_bbox(result_dir, spec["id"], pcd_path)
        bmin = np.array(bbox[:3], dtype=np.float64)
        bmax = np.array(bbox[3:], dtype=np.float64)
        global_min = np.minimum(global_min, bmin)
        global_max = np.maximum(global_max, bmax)
        item = dict(spec)
        item.update(
            {
                "points": header["points"],
                "bytes": pcd_path.stat().st_size,
                "bboxMin": bmin.tolist(),
                "bboxMax": bmax.tolist(),
            }
        )
        datasets.append(item)
        print(f"[OK] {spec['id']} points={header['points']} bytes={pcd_path.stat().st_size}")

    manifest = {
        "title": title,
        "strideBytes": 16,
        "datasets": datasets,
        "globalBboxMin": global_min.tolist(),
        "globalBboxMax": global_max.tolist(),
        "globalCenter": ((global_min + global_max) * 0.5).tolist(),
        "globalSpan": (global_max - global_min).tolist(),
        "notes": "PCD 直读模式：不额外生成 .bin；颜色按 PCD rgb 字段解析。",
    }
    (viewer_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (viewer_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    return viewer_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    viewer = create_viewer(args.result_dir, args.title)
    print(f"[OK] viewer={viewer / 'index.html'}")


if __name__ == "__main__":
    main()
