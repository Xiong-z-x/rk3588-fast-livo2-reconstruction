# Calibration Workflow

## Camera Intrinsics

The camera model is pinhole with radial-tangential distortion. The project configuration files store:

- image width and height
- `fx`, `fy`, `cx`, `cy`
- distortion coefficients
- rectified projection matrix when available

Public templates keep the calibrated numeric model but remove device serial numbers.

## Visual-LiDAR Extrinsics

The visual-LiDAR extrinsic workflow uses targetless calibration based on `direct_visual_lidar_calibration`.

General procedure:

1. Record a bag containing LiDAR, IMU and camera topics.
2. Preprocess synchronized visual-LiDAR frames.
3. Provide an initial transform using manual correspondence or a coarse estimate.
4. Run calibration optimization.
5. Export the transform and convert it to the convention expected by FAST-LIVO2.

## Convention Check

One important integration detail is transform direction. Calibration tools and FAST-LIVO2 can expect different forms of camera-to-LiDAR or LiDAR-to-camera transforms. The project keeps `Rcl` and `Pcl` in the FAST-LIVO2 adaptation config and treats transform direction as a first-class validation item.

## Validation

Calibration should be checked using:

- visual overlay quality
- number of colored map points
- whether image content projects to plausible surfaces
- static pose continuity
- point cloud consistency across looped scene motion
