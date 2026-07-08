# YOLOv8n Checkpoint

This directory contains a real public Ultralytics YOLOv8n pretrained checkpoint:

- File: `yolov8n.pt`
- Source: `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt`
- SHA256: `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`
- Size: `6549796` bytes
- License: `AGPL-3.0`

The runtime uses this file through `cloudmeasure_edge/bev_yolo_detector.py`.
The adapter converts FAST-LIVO2 point cloud ROI data into a three-channel BEV
image and runs YOLO as a candidate detector or fine-tuning initialization
module.
