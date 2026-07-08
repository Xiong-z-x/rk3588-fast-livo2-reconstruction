# CloudMeasure Edge AI Runtime

This folder contains the production-shaped runtime code for the two AI
extensions added on top of the FAST-LIVO2 point cloud reconstruction package:

1. RK3588 NPU point cloud instance segmentation and VoxelNet-Mini recognition.
2. Neural occupancy field based per-cargo volume estimation.
3. BEV-YOLO candidate detection using a real third-party YOLO checkpoint.

The code is organized as a runtime package. It loads model files from
configured paths, calls RKNN Runtime through
`rknnlite.api.RKNNLite`, parses real `/sys/kernel/debug/rknpu/load` output, and
raises errors when model files or board runtime dependencies are missing.

## Expected model artifacts

Place these files on the ELF2 / RK3588 board or mount them into the runtime
container:

- `models/cargo_instance_seg_int8.rknn`
- `models/voxelnet_mini_cargo_cls_int8.rknn`
- `models/neural_occupancy_field.pt`
- `models/third_party/yolo/yolov8n.pt`

The default paths are defined in `configs/edge_runtime.yaml`.

The YOLO checkpoint is a public Ultralytics YOLOv8n pretrained weight. It is
not a cargo-specific trained model by itself; this package uses it through
`cloudmeasure_edge/bev_yolo_detector.py` as a BEV candidate detector and as a
real initialization checkpoint for later cargo-domain fine-tuning.

Model source, export, conversion, and verification commands are listed in:

- `configs/model_manifest.yaml`

The codebase includes the scripts needed to export ONNX architectures, convert
ONNX to RKNN, train the occupancy field checkpoint, and write a runtime
benchmark JSON file.

## Main entry points

- `cloudmeasure_edge/rknn_runtime.py`
  Loads RKNN models, initializes RK3588 NPU cores, and runs inference. The
  pipeline keeps this runtime initialized across frames.

- `cloudmeasure_edge/pointcloud_segmentation.py`
  Converts FAST-LIVO2 PCD ROI points into BEV/Pillar features, runs the NPU
  segmentation model, and converts model output into object instances. It
  supports both objectness-map output and center-head output
  `heatmap + offset + dimensions + yaw`.

- `cloudmeasure_edge/voxelnet_mini.py`
  Builds a local voxel tensor for each segmented object and runs VoxelNet-Mini
  recognition through RKNN Runtime.

- `cloudmeasure_edge/bev_yolo_detector.py`
  Converts ROI point clouds into a three-channel BEV image
  `density + normalized_z_max + valid_cell`, runs the YOLO checkpoint through
  Ultralytics, and maps detected BEV boxes back to metric point subsets.

- `cloudmeasure_edge/occupancy_field.py`
  Loads a PyTorch neural occupancy field checkpoint and estimates object volume
  by sampling inside each fitted OBB.

- `cloudmeasure_edge/pipeline.py`
  Connects PCD loading, NPU segmentation, VoxelNet recognition, occupancy volume
  estimation, and NPU load monitoring into one result object.

- `cloudmeasure_edge/api.py`
  FastAPI endpoints for integration with the web dashboard.

- `scripts/export_reference_models.py`
  Exports the segmentation and VoxelNet-Mini ONNX model definitions and the
  occupancy field checkpoint structure.

- `scripts/export_occupancy_to_onnx.py`
  Exports a trained occupancy checkpoint to ONNX. The default runtime is
  PyTorch (`occupancy.runtime: torch`), and this script provides the conversion
  path for later RKNN deployment.

- `scripts/run_bev_yolo.py`
  Runs the BEV-YOLO detector against a PCD ROI and prints JSON detections,
  including BEV boxes, mapped metric boxes, point counts, and fitted OBB volume
  where enough points are available.

- `scripts/export_yolo_to_onnx.py`
  Exports the included `yolov8n.pt` checkpoint to ONNX so the BEV-YOLO branch
  can follow the same ONNX to RKNN deployment path as the other models.

- `scripts/convert_onnx_to_rknn.py`
  Converts ONNX models to RKNN with RKNN Toolkit 2.

- `scripts/verify_model_artifacts.py`
  Checks required model files and writes size plus SHA256 metadata.

- `scripts/benchmark_edge_pipeline.py`
  Runs warmup plus repeated inference and writes mean / P95 timing and NPU
  utilization.

- `scripts/build_clean_archive.sh`
  Builds a clean submission zip without macOS metadata, build outputs, caches,
  or dependency folders.

- `training/train_occupancy_field.py`
  Trains the occupancy field from an NPZ dataset containing `query_xyz`,
  `context`, and `occupancy` arrays.

## Example

```bash
python -m cloudmeasure_edge.pipeline \
  --config configs/edge_runtime.yaml \
  --pcd /data/cloudmeasure/pcd/fast_livo2_colored_map.pcd \
  --bbox-min -2 -2 -0.2 \
  --bbox-max 4 3 2.5
```

Run the BEV-YOLO branch:

```bash
python scripts/run_bev_yolo.py \
  --config configs/edge_runtime.yaml \
  --pcd /data/cloudmeasure/pcd/fast_livo2_colored_map.pcd \
  --bbox-min -2 -2 -0.2 \
  --bbox-max 4 3 2.5
```

## API and GUI

Run the API:

```bash
uvicorn cloudmeasure_edge.api:app --host 127.0.0.1 --port 8788
```

The web dashboard client calls:

```text
POST /api/edge-ai/segment-recognize-volume
```

and renders per-cargo label, confidence, occupied volume, total volume, timing,
and NPU load.
