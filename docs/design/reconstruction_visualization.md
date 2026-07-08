# Reconstruction and Visualization

## Reconstruction Modes

### FAST-LIVO2 Mode

FAST-LIVO2 mode consumes LiDAR, IMU and camera image topics. It produces a colored point cloud and a pose trajectory when camera timestamps and extrinsics are valid.

### ONLY_LIO Mode

ONLY_LIO mode disables image input and uses Mid-360 LiDAR + IMU for pose estimation. It is used when camera triggering is unavailable or when a LiDAR-only quality baseline is needed.

## Point Cloud Layers

The visualization pipeline separates layers by meaning:

- colored FAST-LIVO2 map
- registered intensity map
- LiDAR-only pose-accumulated height-colored full map
- stride-10 preview layers
- raw Livox accumulation layers
- pose trajectory

This separation prevents confusing a camera-colored result with a LiDAR-only height-colored result.

## WebGL Viewer Requirements

The static viewer supports:

- unrestricted 360-degree rotation
- mouse wheel zoom
- middle-button pan
- right-button vertical zoom
- `Shift + left button` pan
- reset, top and front views
- hideable side panel
- trajectory rendered as `LINE_STRIP + POINTS`

The trajectory is drawn as an overlay with depth testing disabled so that dense point clouds do not hide the motion path.

## Progressive Reconstruction

The progressive viewer uses `lidar_poses.txt` and raw bag or mapped point data to generate frame-indexed reconstruction playback. This makes the final model appear over time and is useful for demos that need to show the mapping process rather than only the final result.
