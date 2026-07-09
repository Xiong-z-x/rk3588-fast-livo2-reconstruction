# Model Directory

Put runtime model artifacts here when running locally, or copy the same files to
the board paths configured in `configs/edge_runtime.yaml`.

Required files:

- `cargo_instance_seg_int8.rknn`
- `voxelnet_mini_cargo_cls_int8.rknn`
- `neural_occupancy_field.pt`
- `third_party/yolo/yolov8n.pt`

The code does not create these files and does not substitute fixed outputs when
they are missing.

`third_party/yolo/yolov8n.pt` is a public Ultralytics YOLOv8n checkpoint used by
the BEV-YOLO adapter as a real pretrained model file. The source URL, checksum,
and intended role are recorded in `../configs/model_manifest.yaml`.
