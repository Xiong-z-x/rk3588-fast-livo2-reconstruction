# Reproduction Guide

This guide describes how to reproduce the submitted ROS1 acquisition and reconstruction stack from a clean checkout or extracted archive.

The package targets an RK3588 / ELF2-class board running ROS1 Noetic in Docker. It is not a Gazebo, planner, or flight-control repository. Flight-control attitude closure is assumed to be handled by the flight controller; this package provides perception acquisition, FAST-LIVO2 reconstruction, calibration scripts, point-cloud processing, WebGL visualization, and a read-only edge status panel.

## 1. Runtime Variables

Set these variables before running host-side helper scripts:

```bash
export RK3588_ROS_CONTAINER=${RK3588_ROS_CONTAINER:-rk3588_dev}
export RK3588_WS=${RK3588_WS:-/root/fast_lio2_ws}
export RK3588_HOST=<board-ip>
```

The default ROS container is `rk3588_dev`. The default workspace path is `/root/fast_lio2_ws`.

## 2. Prepare Local Hardware Config

Template files are deliberately named `.example.*` and are not directly runnable. Copy them to local config names and fill in real hardware values:

```bash
cp 00_project_configuration/livox_mid360_network.example.yaml 00_project_configuration/livox_mid360_network.local.yaml
cp 00_project_configuration/hikrobot_camera_trigger.example.yaml 00_project_configuration/hikrobot_camera_trigger.local.yaml
cp 07_full_source_code/livox_ros_driver2_project_config/config/MID360_config_rk3588.example.json \
   07_full_source_code/livox_ros_driver2_project_config/config/MID360_config_rk3588.local.json
cp 07_full_source_code/mvs_ros_driver_project_config/config/left_camera_trigger.example.yaml \
   07_full_source_code/mvs_ros_driver_project_config/config/left_camera_trigger.local.yaml
```

Fill in the Mid-360 broadcast code, LiDAR IP, host NIC IP, Hikrobot serial number, and camera trigger settings before launching sensors.

Validate the local files before use:

```bash
python3 00_project_configuration/validate_local_configs.py \
  00_project_configuration/livox_mid360_network.local.yaml \
  00_project_configuration/hikrobot_camera_trigger.local.yaml \
  07_full_source_code/livox_ros_driver2_project_config/config/MID360_config_rk3588.local.json \
  07_full_source_code/mvs_ros_driver_project_config/config/left_camera_trigger.local.yaml
```

## 3. Assemble ROS1 Workspace

From the extracted repository root:

```bash
./00_project_configuration/create_catkin_workspace_from_submission.sh \
  --workspace "$RK3588_WS" \
  --copy
```

Use `--with-calibration` only when the review machine also has the dependencies required by `direct_visual_lidar_calibration`.

Build:

```bash
cd "$RK3588_WS"
catkin_make
source devel/setup.bash
```

Vendor prerequisites still apply: Livox SDK / Livox ROS Driver2 requirements, Hikrobot MVS SDK, ROS1 Noetic, PCL, OpenCV, Eigen and the FAST-LIVO2 dependencies.

## 4. Start Acquisition

Raw LiDAR + IMU + camera bag:

```bash
01_acquisition_and_recording/raw_full_bag_recording/host_start_raw_bag.sh demo_scene
01_acquisition_and_recording/raw_full_bag_recording/host_stop_raw_bag.sh
```

LiDAR-only bag:

```bash
LIO_BAG_DURATION_SEC=180 \
01_acquisition_and_recording/lidar_only_recording/host_start_lidar_only_bag.sh demo_lio_scene
```

## 5. Run Offline Reconstruction

FAST-LIVO2 visual-LiDAR reconstruction:

```bash
FAST_LIVO2_PLAY_RATE=0.5 \
FAST_LIVO2_POST_PLAY_WAIT_SEC=60 \
02_reconstruction_and_mapping/fast_livo2_offline/run_fast_livo2_offline_bag.sh \
  /path/to/raw.bag /path/to/run_dir
```

ONLY_LIO reconstruction:

```bash
FAST_LIVO2_PLAY_RATE=0.5 \
FAST_LIVO2_POST_PLAY_WAIT_SEC=60 \
02_reconstruction_and_mapping/fast_livo2_only_lio_offline/run_fast_livo2_only_lio_offline_bag.sh \
  /path/to/lidar_only.bag /path/to/run_dir
```

Expected outputs include `all_raw_points.pcd`, registered intensity PCD, `lidar_poses.txt`, pose-accumulated height-colored LiDAR point clouds, stride previews, and WebGL viewer files depending on the run mode.

## 6. Hardware Trigger Interpretation

The Hikrobot driver sets:

- `TriggerEnable`
- `TriggerMode`
- `TriggerSource`
- `LineSelector`

The driver prints the effective values at startup. For the competition hardware, verify from the Hikrobot MVS SDK feature tree that the selected numeric enum maps to the physical trigger line used by the STM32. The code package does not claim camera exposure timestamps are embedded in ROS messages: image messages use `ros::Time::now()` when publishing. The intended engineering statement is that STM32 external trigger controls camera exposure cadence, while ROS timestamps are used for ROS-side approximate alignment unless hardware timestamp/error statistics are supplied.

## 7. Runtime Status Panel

Start the read-only backend:

```bash
python3 05_realtime_display/tools/rk3588_edge_status_server.py \
  --host 127.0.0.1 \
  --port 8766 \
  --container "$RK3588_ROS_CONTAINER" \
  --workspace "$RK3588_WS"
```

Start the web app:

```bash
cd 05_realtime_display/web_dashboard
npm ci
npm run dev
```

This panel reports Docker, ROS topics, CPU, memory and RKNPU status. It is an edge status panel, not a full measurement GUI by itself. Full point-cloud viewing is provided by the WebGL viewers under `04_visualization`.

## 8. Verification Commands

Run before packaging:

```bash
python3 06_source_manifests/verify_submission_static.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s 05_realtime_display/tools/tests
npm --prefix 05_realtime_display/web_dashboard run build
```

If unit tests are run without `PYTHONDONTWRITEBYTECODE=1`, remove generated `__pycache__` directories before packaging.
