#!/usr/bin/env python3
"""Create a progressive WebGL reconstruction viewer from FAST-LIVO2 outputs.

The primary dataset uses exact per-scan boundaries recovered from the raw bag
frame index. The FAST-LIVO2 registered-intensity dataset is split over the same
pose timeline using the LiDAR frame point-count distribution because the
registered PCD itself does not carry per-scan boundary metadata.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


POINT_STRIDE_BYTES = 16


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _parse_pcd_header(path: Path) -> Tuple[int, int, Dict[str, str]]:
    header: Dict[str, str] = {}
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise RuntimeError(f"{path} ended before DATA line")
            text = line.decode("ascii", errors="replace").strip()
            if text:
                parts = text.split(maxsplit=1)
                if len(parts) == 2:
                    header[parts[0]] = parts[1]
            if text == "DATA binary":
                data_offset = handle.tell()
                break
    points = int(header.get("POINTS", header.get("WIDTH", "0")))
    fields = header.get("FIELDS", "")
    sizes = header.get("SIZE", "")
    types = header.get("TYPE", "")
    if fields != "x y z rgb" or sizes != "4 4 4 4" or types != "F F F U":
        raise RuntimeError(
            f"{path.name} is not WebGL x y z rgb binary PCD: "
            f"FIELDS={fields!r} SIZE={sizes!r} TYPE={types!r}"
        )
    expected_size = data_offset + points * POINT_STRIDE_BYTES
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(
            f"{path.name} size mismatch: expected {expected_size}, got {actual_size}"
        )
    return data_offset, points, header


def _copy_range(
    src_path: Path,
    data_offset: int,
    point_start: int,
    point_count: int,
    dst_path: Path,
) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    byte_count = point_count * POINT_STRIDE_BYTES
    remaining = byte_count
    with src_path.open("rb") as src, dst_path.open("wb") as dst:
        src.seek(data_offset + point_start * POINT_STRIDE_BYTES)
        while remaining:
            chunk = src.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                raise RuntimeError(f"Unexpected EOF while copying {src_path}")
            dst.write(chunk)
            remaining -= len(chunk)


def _allocate_weighted(total: int, weights: Sequence[int]) -> List[int]:
    if total < 0:
        raise ValueError("total must be non-negative")
    weight_sum = sum(weights)
    if weight_sum <= 0:
        base = total // len(weights)
        counts = [base] * len(weights)
        for idx in range(total - base * len(weights)):
            counts[idx] += 1
        return counts
    raw = [(total * weight) / weight_sum for weight in weights]
    counts = [math.floor(value) for value in raw]
    remaining = total - sum(counts)
    order = sorted(range(len(raw)), key=lambda idx: raw[idx] - counts[idx], reverse=True)
    for idx in order[:remaining]:
        counts[idx] += 1
    if sum(counts) != total:
        raise RuntimeError("weighted allocation failed")
    return counts


def _with_point_starts(counts: Sequence[int]) -> List[Dict[str, int]]:
    point_start = 0
    out: List[Dict[str, int]] = []
    for count in counts:
        out.append({"pointStart": point_start, "pointCount": int(count)})
        point_start += int(count)
    return out


def _chunk_dataset(
    *,
    dataset_id: str,
    src_pcd: Path,
    out_dir: Path,
    frame_counts: Sequence[int],
    frames_per_chunk: int,
) -> Tuple[List[Dict[str, Any]], int]:
    data_offset, total_points, _header = _parse_pcd_header(src_pcd)
    if sum(frame_counts) != total_points:
        raise RuntimeError(
            f"{dataset_id} point count mismatch: frame sum {sum(frame_counts)} != PCD {total_points}"
        )

    chunks: List[Dict[str, Any]] = []
    chunk_dir = out_dir / "data" / dataset_id
    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    point_start = 0
    chunk_index = 0
    for start_frame in range(0, len(frame_counts), frames_per_chunk):
        end_frame = min(len(frame_counts), start_frame + frames_per_chunk)
        point_count = int(sum(frame_counts[start_frame:end_frame]))
        file_name = f"data/{dataset_id}/chunk_{chunk_index:04d}.bin"
        dst_path = out_dir / file_name
        _copy_range(src_pcd, data_offset, point_start, point_count, dst_path)
        chunks.append(
            {
                "index": chunk_index,
                "file": file_name.replace("\\", "/"),
                "startFrame": start_frame,
                "endFrame": end_frame,
                "pointStart": point_start,
                "pointCount": point_count,
                "bytes": point_count * POINT_STRIDE_BYTES,
            }
        )
        point_start += point_count
        chunk_index += 1
    return chunks, total_points


def _build_frames(frame_index: Dict[str, Any], fast_counts: Sequence[int]) -> List[Dict[str, Any]]:
    lidar_frames = frame_index["frames"]
    lidar_points = _with_point_starts([int(frame["point_count"]) for frame in lidar_frames])
    fast_points = _with_point_starts(fast_counts)
    frames: List[Dict[str, Any]] = []
    for frame, lidar, fast in zip(lidar_frames, lidar_points, fast_points):
        frames.append(
            {
                "frameIndex": int(frame["frame_index"]),
                "scanIndex": int(frame["scan_index"]),
                "stamp": float(frame["stamp"]),
                "poseTime": float(frame["pose_time"]),
                "relTime": float(frame["rel_time"]),
                "poseDt": float(frame["pose_dt"]),
                "poseIndex": int(frame["pose_index"]),
                "position": [float(v) for v in frame["position"]],
                "quaternionXyzw": [float(v) for v in frame["quaternion_xyzw"]],
                "points": {
                    "lidar_height": lidar,
                    "fast_livo_intensity": fast,
                },
            }
        )
    return frames


def _bbox_from_manifest(result_dir: Path) -> Dict[str, Any]:
    manifest_path = result_dir / "webgl_viewer" / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = _read_json(manifest_path)
    return {
        "globalBboxMin": manifest.get("globalBboxMin"),
        "globalBboxMax": manifest.get("globalBboxMax"),
        "globalCenter": manifest.get("globalCenter"),
        "globalSpan": manifest.get("globalSpan"),
    }


def _viewer_html() -> str:
    return r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Progressive LiDAR-only Reconstruction</title>
  <style>
    :root { color-scheme: light; --bg:#f7f8fa; --panel:rgba(255,255,255,.96); --line:#d5dbe3; --text:#162033; --muted:#5c697b; --accent:#0b72b9; --danger:#b42318; }
    html, body { margin:0; width:100%; height:100%; overflow:hidden; font-family:Segoe UI, Arial, "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--text); }
    canvas { position:fixed; inset:0; width:100vw; height:100vh; display:block; }
    .panel { position:fixed; left:16px; top:16px; width:520px; max-width:calc(100vw - 32px); max-height:calc(100vh - 32px); overflow:auto; padding:14px 16px; background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 10px 30px rgba(20,32,51,.14); backdrop-filter:blur(8px); }
    h1 { margin:0 0 6px; font-size:18px; line-height:1.25; font-weight:650; letter-spacing:0; }
    .sub { font-size:12px; color:var(--muted); line-height:1.45; margin-bottom:12px; }
    .row { display:grid; grid-template-columns:120px 1fr; align-items:center; gap:10px; margin:9px 0; }
    label { font-size:12px; color:var(--muted); }
    select, button, input[type="range"] { width:100%; box-sizing:border-box; }
    button, select { height:32px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--text); font-size:13px; }
    button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
    .buttons { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }
    .checks { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; font-size:12px; color:var(--text); }
    .checks label { display:flex; gap:6px; align-items:center; color:var(--text); }
    pre { margin:10px 0 0; padding:10px; background:#111827; color:#dbeafe; border-radius:6px; white-space:pre-wrap; font-size:12px; line-height:1.45; }
    .bar { height:8px; background:#e5e7eb; border-radius:999px; overflow:hidden; border:1px solid #d1d5db; }
    .bar > div { height:100%; width:0%; background:linear-gradient(90deg,#0b72b9,#2fb170); }
  </style>
</head>
<body>
  <canvas id="gl"></canvas>
  <div class="panel">
    <h1>逐步建模展示</h1>
    <div class="sub">按原始 /livox/lidar scan 与 FAST-LIVO2 位姿匹配顺序逐帧累积。默认显示 LiDAR-only 位姿累计高度着色点云，不包含相机 RGB。</div>
    <div class="row"><label>数据层</label><select id="dataset"></select></div>
    <div class="row"><label>播放控制</label><div class="buttons"><button id="play" class="primary">播放</button><button id="restart">重播</button><button id="reset">重置视角</button></div></div>
    <div class="row"><label>速度</label><select id="speed"><option value="1">1x 真实时间</option><option value="2">2x</option><option value="5">5x</option><option value="10" selected>10x 展示</option><option value="20">20x</option><option value="40">40x 快速</option></select></div>
    <div class="row"><label>进度</label><input id="frame" type="range" min="0" value="0" step="1" /></div>
    <div class="bar"><div id="bar"></div></div>
    <div class="row"><label>显示</label><div class="checks"><label><input id="showCloud" type="checkbox" checked />累计点云</label><label><input id="showCurrent" type="checkbox" checked />当前帧</label><label><input id="showTrajectory" type="checkbox" checked />轨迹</label></div></div>
    <div class="row"><label>点大小</label><input id="pointSize" type="range" min="0.3" max="3.0" value="1.0" step="0.1" /></div>
    <pre id="stats">加载 manifest...</pre>
  </div>
  <script>
    const canvas=document.getElementById("gl");
    const gl=canvas.getContext("webgl",{antialias:false,powerPreference:"high-performance"});
    if(!gl) throw new Error("WebGL unavailable");
    const vs=`attribute vec3 aPosition; attribute vec4 aColorBgra; uniform mat4 uMvp; uniform float uPointSize; uniform float uAlpha; varying vec4 vColor; void main(){ gl_Position=uMvp*vec4(aPosition,1.0); gl_PointSize=uPointSize; vColor=vec4(aColorBgra.b,aColorBgra.g,aColorBgra.r,uAlpha); }`;
    const fs=`precision mediump float; varying vec4 vColor; void main(){ gl_FragColor=vColor; }`;
    function shader(type,src){ const s=gl.createShader(type); gl.shaderSource(s,src); gl.compileShader(s); if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
    const program=gl.createProgram(); gl.attachShader(program,shader(gl.VERTEX_SHADER,vs)); gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs)); gl.linkProgram(program); gl.useProgram(program);
    const loc={pos:gl.getAttribLocation(program,"aPosition"),col:gl.getAttribLocation(program,"aColorBgra"),mvp:gl.getUniformLocation(program,"uMvp"),point:gl.getUniformLocation(program,"uPointSize"),alpha:gl.getUniformLocation(program,"uAlpha")};
    gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
    const dbg=gl.getExtension("WEBGL_debug_renderer_info");
    const gpu=dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
    let manifest=null, active=null, chunks=[], frameToChunk=[], buffers=new Map(), loading=new Set(), loadQueue=[], inFlight=0, datasetToken=0;
    let yaw=-0.75, pitch=-0.75, dist=14, pan=[0,0,0], dragging=false, last=[0,0], mode="rotate";
    let playing=false, currentFrame=0, simTime=0, lastTick=0, renderPending=false, trajectoryBuffer=null;
    function wrapAngle(a){ const two=Math.PI*2; return ((a+Math.PI)%two+two)%two-Math.PI; }
    function matMul(a,b){ const o=new Float32Array(16); for(let r=0;r<4;r++)for(let c=0;c<4;c++)o[c*4+r]=a[0*4+r]*b[c*4+0]+a[1*4+r]*b[c*4+1]+a[2*4+r]*b[c*4+2]+a[3*4+r]*b[c*4+3]; return o; }
    function perspective(fovy,aspect,near,far){ const f=1/Math.tan(fovy/2), nf=1/(near-far); return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]); }
    function translate(x,y,z){ return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,x,y,z,1]); }
    function rotX(a){ const c=Math.cos(a),s=Math.sin(a); return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]); }
    function rotZ(a){ const c=Math.cos(a),s=Math.sin(a); return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]); }
    function resize(){ const dpr=Math.min(devicePixelRatio||1,2); const w=Math.floor(innerWidth*dpr), h=Math.floor(innerHeight*dpr); if(canvas.width!==w||canvas.height!==h){ canvas.width=w; canvas.height=h; gl.viewport(0,0,w,h); } }
    function resetView(){ const span=Math.max(...manifest.globalSpan); dist=span*1.85+1; yaw=-0.75; pitch=-0.75; pan=[-manifest.globalCenter[0],-manifest.globalCenter[1],-manifest.globalCenter[2]]; requestRender(); }
    function mvp(){ const aspect=canvas.width/canvas.height; let p=perspective(Math.PI/4,aspect,0.01,10000); let v=translate(0,0,-dist); v=matMul(v,rotX(pitch)); v=matMul(v,rotZ(yaw)); v=matMul(v,translate(pan[0],pan[1],pan[2])); return matMul(p,v); }
    function requestRender(){ if(renderPending) return; renderPending=true; requestAnimationFrame(()=>{ renderPending=false; draw(); }); }
    function setAttribs(){ gl.enableVertexAttribArray(loc.pos); gl.vertexAttribPointer(loc.pos,3,gl.FLOAT,false,16,0); gl.enableVertexAttribArray(loc.col); gl.vertexAttribPointer(loc.col,4,gl.UNSIGNED_BYTE,true,16,12); }
    function findFrameByTime(t){ const frames=manifest.frames; let lo=0, hi=frames.length-1; if(t<=0) return 0; if(t>=frames[hi].relTime) return hi; while(lo<hi){ const mid=(lo+hi+1)>>1; if(frames[mid].relTime<=t) lo=mid; else hi=mid-1; } return lo; }
    function clearDatasetBuffers(){ datasetToken++; for(const b of buffers.values()) gl.deleteBuffer(b); buffers.clear(); loading.clear(); loadQueue=[]; inFlight=0; }
    function selectDataset(id){ clearDatasetBuffers(); active=manifest.datasets.find(d=>d.id===id); chunks=active.chunks; frameToChunk=new Array(manifest.frames.length); chunks.forEach(c=>{ for(let i=c.startFrame;i<c.endFrame;i++) frameToChunk[i]=c.index; }); currentFrame=0; simTime=0; playing=false; document.getElementById("play").textContent="播放"; queueChunksThrough(0, 4); updateUi(); requestRender(); }
    function queueChunk(idx){ if(idx<0||idx>=chunks.length||buffers.has(idx)||loading.has(idx)||loadQueue.includes(idx)) return; loadQueue.push(idx); pumpQueue(); }
    function queueChunksThrough(frame, extraChunks){ const idx=frameToChunk[Math.max(0,Math.min(frame,manifest.frames.length-1))]||0; for(let i=0;i<=Math.min(chunks.length-1,idx+extraChunks);i++) queueChunk(i); }
    function pumpQueue(){ while(inFlight<3 && loadQueue.length){ const idx=loadQueue.shift(); if(buffers.has(idx)||loading.has(idx)) continue; const chunk=chunks[idx]; const token=datasetToken; loading.add(idx); inFlight++; fetch(chunk.file).then(r=>{ if(!r.ok) throw new Error(`${chunk.file} ${r.status}`); return r.arrayBuffer(); }).then(buf=>{ if(token!==datasetToken) return; const b=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,b); gl.bufferData(gl.ARRAY_BUFFER,new Uint8Array(buf),gl.STATIC_DRAW); buffers.set(idx,b); }).catch(err=>{ console.error(err); }).finally(()=>{ if(token!==datasetToken) return; loading.delete(idx); inFlight--; pumpQueue(); updateUi(); requestRender(); }); } }
    function readyThrough(frame){ const idx=frameToChunk[frame]||0; for(let i=0;i<=idx;i++){ if(!buffers.has(i)) return false; } return true; }
    function framePointInfo(frameIdx){ const f=manifest.frames[frameIdx]; return f.points[active.id]; }
    function pointsToFrame(frameIdx){ const info=framePointInfo(frameIdx); return info.pointStart+info.pointCount; }
    function drawCloud(matrix){ if(!document.getElementById("showCloud").checked) return; const targetPoints=pointsToFrame(currentFrame); const scale=Number(document.getElementById("pointSize").value); for(const c of chunks){ if(c.pointStart>=targetPoints) break; const b=buffers.get(c.index); if(!b) continue; const n=Math.min(c.pointCount, targetPoints-c.pointStart); if(n<=0) continue; gl.bindBuffer(gl.ARRAY_BUFFER,b); setAttribs(); gl.uniformMatrix4fv(loc.mvp,false,matrix); gl.uniform1f(loc.point,active.pointSize*scale); gl.uniform1f(loc.alpha,active.alpha); gl.drawArrays(gl.POINTS,0,n); } }
    function drawCurrentScan(matrix){ if(!document.getElementById("showCurrent").checked) return; const chunkIdx=frameToChunk[currentFrame]; const b=buffers.get(chunkIdx); if(!b) return; const c=chunks[chunkIdx]; const info=framePointInfo(currentFrame); const local=info.pointStart-c.pointStart; if(info.pointCount<=0) return; gl.bindBuffer(gl.ARRAY_BUFFER,b); setAttribs(); gl.uniformMatrix4fv(loc.mvp,false,matrix); gl.uniform1f(loc.point,Math.max(2.5,active.pointSize*2.8)); gl.uniform1f(loc.alpha,1.0); gl.drawArrays(gl.POINTS,local,info.pointCount); }
    function buildTrajectory(){ const frames=manifest.frames; const arr=new ArrayBuffer(frames.length*16); const dv=new DataView(arr); frames.forEach((f,i)=>{ const o=i*16; dv.setFloat32(o+0,f.position[0],true); dv.setFloat32(o+4,f.position[1],true); dv.setFloat32(o+8,f.position[2],true); dv.setUint32(o+12,(255<<16)|(40<<8)|40,true); }); trajectoryBuffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,trajectoryBuffer); gl.bufferData(gl.ARRAY_BUFFER,new Uint8Array(arr),gl.STATIC_DRAW); }
    function drawTrajectory(matrix){ if(!document.getElementById("showTrajectory").checked || !trajectoryBuffer) return; gl.bindBuffer(gl.ARRAY_BUFFER,trajectoryBuffer); setAttribs(); gl.uniformMatrix4fv(loc.mvp,false,matrix); gl.uniform1f(loc.alpha,1.0); gl.uniform1f(loc.point,5.0); gl.drawArrays(gl.LINE_STRIP,0,currentFrame+1); gl.drawArrays(gl.POINTS,0,currentFrame+1); }
    function draw(){ resize(); gl.clearColor(.965,.972,.982,1); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT); if(!manifest||!active) return; const matrix=mvp(); drawCloud(matrix); drawCurrentScan(matrix); drawTrajectory(matrix); }
    function updateUi(){ if(!manifest||!active) return; const f=manifest.frames[currentFrame]; const info=framePointInfo(currentFrame); const pointEnd=pointsToFrame(currentFrame); const percent=100*currentFrame/(manifest.frames.length-1); document.getElementById("frame").value=String(currentFrame); document.getElementById("bar").style.width=percent.toFixed(2)+"%"; const chunkIdx=frameToChunk[currentFrame]||0; const loaded=[...buffers.keys()].length; const status=readyThrough(currentFrame)?"播放就绪":"加载中"; document.getElementById("stats").textContent=[`数据层: ${active.name}`,`状态: ${status} | GPU: ${gpu}`,`时间: ${f.relTime.toFixed(2)} / ${manifest.durationSec.toFixed(2)} s`, `scan: ${currentFrame+1} / ${manifest.frameCount} | 原始 scan index: ${f.scanIndex}`, `累计点数: ${pointEnd.toLocaleString()} / ${active.pointCount.toLocaleString()}`, `当前帧点数: ${info.pointCount.toLocaleString()} | pose_dt: ${f.poseDt.toFixed(4)} s`, `分块: ${loaded} / ${chunks.length} loaded | in-flight ${inFlight}`, active.note].join("\n"); }
    function tick(ts){ if(!lastTick) lastTick=ts; const dt=(ts-lastTick)/1000; lastTick=ts; if(playing&&manifest&&active){ queueChunksThrough(currentFrame,4); if(readyThrough(currentFrame)){ simTime+=dt*Number(document.getElementById("speed").value); if(simTime>=manifest.durationSec){ simTime=manifest.durationSec; playing=false; document.getElementById("play").textContent="播放"; } currentFrame=findFrameByTime(simTime); } updateUi(); requestRender(); } requestAnimationFrame(tick); }
    function setupUi(){ const ds=document.getElementById("dataset"); manifest.datasets.forEach(d=>{ const o=document.createElement("option"); o.value=d.id; o.textContent=d.name; ds.appendChild(o); }); ds.value=manifest.datasets.find(d=>d.default)?.id||manifest.datasets[0].id; ds.onchange=()=>selectDataset(ds.value); const slider=document.getElementById("frame"); slider.max=String(manifest.frames.length-1); slider.oninput=()=>{ currentFrame=Number(slider.value); simTime=manifest.frames[currentFrame].relTime; queueChunksThrough(currentFrame,4); updateUi(); requestRender(); }; document.getElementById("play").onclick=()=>{ playing=!playing; document.getElementById("play").textContent=playing?"暂停":"播放"; lastTick=0; }; document.getElementById("restart").onclick=()=>{ currentFrame=0; simTime=0; playing=true; document.getElementById("play").textContent="暂停"; updateUi(); requestRender(); }; document.getElementById("reset").onclick=resetView; ["showCloud","showCurrent","showTrajectory","pointSize"].forEach(id=>document.getElementById(id).addEventListener("input",()=>{ updateUi(); requestRender(); })); buildTrajectory(); resetView(); selectDataset(ds.value); }
    canvas.addEventListener("contextmenu",e=>e.preventDefault());
    canvas.addEventListener("mousedown",e=>{ dragging=true; last=[e.clientX,e.clientY]; mode=(e.button===1||e.shiftKey)?"pan":e.button===2?"zoom":"rotate"; });
    addEventListener("mouseup",()=>dragging=false);
    addEventListener("mousemove",e=>{ if(!dragging) return; const dx=e.clientX-last[0], dy=e.clientY-last[1]; last=[e.clientX,e.clientY]; if(mode==="rotate"){ yaw=wrapAngle(yaw+dx*.006); pitch=wrapAngle(pitch+dy*.006); } else if(mode==="pan"){ pan[0]+=dx*dist*.0009; pan[1]-=dy*dist*.0009; } else { dist*=Math.exp(dy*.01); } requestRender(); });
    canvas.addEventListener("wheel",e=>{ e.preventDefault(); dist*=Math.exp(e.deltaY*.001); requestRender(); },{passive:false});
    addEventListener("resize",requestRender);
    fetch("manifest.json?rev=progressive_20260705").then(r=>r.json()).then(m=>{ manifest=m; setupUi(); requestAnimationFrame(tick); }).catch(err=>{ document.getElementById("stats").textContent=String(err); });
  </script>
</body>
</html>
'''


def create_viewer(result_dir: Path, frames_json: Path, out_dir: Path, frames_per_chunk: int) -> Dict[str, Any]:
    frame_index = _read_json(frames_json)
    frame_count = int(frame_index["matched_frames"])
    if frame_count != len(frame_index["frames"]):
        raise RuntimeError("frame index summary does not match frames length")
    lidar_counts = [int(frame["point_count"]) for frame in frame_index["frames"]]

    if out_dir.exists():
        for child in out_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    lidar_pcd = result_dir / "lidar_pose_mapped_height_full.pcd"
    fast_pcd = result_dir / "fast_livo2_only_lio_registered_intensity_webgl_full.pcd"
    if not fast_pcd.exists():
        fast_pcd = result_dir / "fast_livo2_only_lio_registered_intensity_full.pcd"
    if not fast_pcd.exists():
        raise RuntimeError(
            "Missing FAST-LIVO2 registered intensity PCD: expected "
            "fast_livo2_only_lio_registered_intensity_webgl_full.pcd or "
            "fast_livo2_only_lio_registered_intensity_full.pcd"
        )
    lidar_data_offset, lidar_points, _ = _parse_pcd_header(lidar_pcd)
    _ = lidar_data_offset
    if sum(lidar_counts) != lidar_points:
        raise RuntimeError(
            f"LiDAR frame counts {sum(lidar_counts)} do not match {lidar_pcd.name} points {lidar_points}"
        )
    _, fast_points, _ = _parse_pcd_header(fast_pcd)
    fast_counts = _allocate_weighted(fast_points, lidar_counts)

    lidar_chunks, lidar_total = _chunk_dataset(
        dataset_id="lidar_height",
        src_pcd=lidar_pcd,
        out_dir=out_dir,
        frame_counts=lidar_counts,
        frames_per_chunk=frames_per_chunk,
    )
    fast_chunks, fast_total = _chunk_dataset(
        dataset_id="fast_livo_intensity",
        src_pcd=fast_pcd,
        out_dir=out_dir,
        frame_counts=fast_counts,
        frames_per_chunk=frames_per_chunk,
    )

    frames = _build_frames(frame_index, fast_counts)
    bbox = _bbox_from_manifest(result_dir)
    manifest: Dict[str, Any] = {
        "title": "new_scene_3min_20260705 progressive LiDAR-only reconstruction",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "frameIndexSource": str(frames_json),
        "frameCount": frame_count,
        "durationSec": float(frame_index.get("duration_sec", frame_index.get("duration", 0.0))),
        "framesPerChunk": frames_per_chunk,
        "pointStrideBytes": POINT_STRIDE_BYTES,
        "sourceBag": frame_index.get("source_bag"),
        "sourcePoses": frame_index.get("source_poses"),
        "poseMatch": {
            "maxPoseDt": frame_index.get("max_pose_dt"),
            "maxObservedPoseDt": frame_index.get("max_pose_match_dt"),
            "unmatchedFrames": frame_index.get("unmatched_frames"),
            "frameTotal": frame_index.get("frame_total"),
        },
        "datasets": [
            {
                "id": "lidar_height",
                "name": "LiDAR-only 位姿累计高度着色",
                "default": True,
                "pointCount": lidar_total,
                "pointSize": 0.9,
                "alpha": 0.92,
                "chunks": lidar_chunks,
                "sourcePcd": lidar_pcd.name,
                "frameBoundary": "exact: raw bag /livox/lidar matched to lidar_poses.txt",
                "note": "按原始 /livox/lidar scan 与 FAST-LIVO2 pose 匹配结果逐帧累积；颜色为高度伪彩色，无相机 RGB。",
            },
            {
                "id": "fast_livo_intensity",
                "name": "FAST-LIVO2 registered intensity",
                "default": False,
                "pointCount": fast_total,
                "pointSize": 0.8,
                "alpha": 0.9,
                "chunks": fast_chunks,
                "sourcePcd": fast_pcd.name,
                "frameBoundary": "estimated: weighted by exact LiDAR scan point counts",
                "note": "FAST-LIVO2 registered intensity 原始 PCD 不含逐 scan 边界；这里沿同一位姿时间轴按 LiDAR 帧点数比例切片，颜色为强度灰度。",
            },
        ],
        "frames": frames,
    }
    manifest.update({k: v for k, v in bbox.items() if v is not None})
    if "globalCenter" not in manifest or "globalSpan" not in manifest:
        positions = [frame["position"] for frame in frames]
        mins = [min(p[i] for p in positions) for i in range(3)]
        maxs = [max(p[i] for p in positions) for i in range(3)]
        manifest["globalBboxMin"] = mins
        manifest["globalBboxMax"] = maxs
        manifest["globalCenter"] = [(mins[i] + maxs[i]) / 2.0 for i in range(3)]
        manifest["globalSpan"] = [maxs[i] - mins[i] for i in range(3)]

    _write_json(out_dir / "manifest.json", manifest)
    (out_dir / "index.html").write_text(_viewer_html(), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--frames-per-chunk", type=int, default=10)
    args = parser.parse_args()

    result_dir = args.result_dir.resolve()
    out_dir = (args.out_dir or result_dir / "progressive_reconstruction_viewer").resolve()
    manifest = create_viewer(result_dir, args.frames_json.resolve(), out_dir, args.frames_per_chunk)
    print(f"OUT_DIR={out_dir}")
    print(f"FRAME_COUNT={manifest['frameCount']}")
    print(f"DURATION_SEC={manifest['durationSec']}")
    for dataset in manifest["datasets"]:
        print(
            f"DATASET={dataset['id']}|POINTS={dataset['pointCount']}|CHUNKS={len(dataset['chunks'])}|BOUNDARY={dataset['frameBoundary']}"
        )


if __name__ == "__main__":
    main()
