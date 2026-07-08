#!/usr/bin/env python3
"""Apply the local Fast-LIVO Mid-360 tutorial adaptation on RK3588.

Scope is intentionally narrow:
- livox_ros_driver -> livox_ros_driver2 for ROS1 driver2 CustomMsg.
- Replace Preprocess::avia_handler with the tutorial Mid-360-compatible body.
- Add project-specific tutorial-style mid360/camera/launch config using saved
  RK3588 Hikrobot intrinsics/extrinsics.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path("/root/fast_lio2_ws/src/FAST-LIVO")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_required(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"pattern not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"start not found in {path}: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"end not found in {path}: {end!r}")
    path.write_text(text[:start_index] + replacement + "\n\n" + text[end_index:], encoding="utf-8")


def adapt_driver2() -> None:
    preprocess_h = ROOT / "include/preprocess.h"
    preprocess_cpp = ROOT / "src/preprocess.cpp"
    laser_cpp = ROOT / "src/laserMapping.cpp"
    cmake = ROOT / "CMakeLists.txt"
    package = ROOT / "package.xml"

    for path in [preprocess_h, preprocess_cpp, laser_cpp]:
        text = path.read_text(encoding="utf-8")
        text = text.replace("livox_ros_driver/CustomMsg.h", "livox_ros_driver2/CustomMsg.h")
        text = text.replace("livox_ros_driver::CustomMsg", "livox_ros_driver2::CustomMsg")
        path.write_text(text, encoding="utf-8")

    text = cmake.read_text(encoding="utf-8")
    if "  livox_ros_driver\n" in text:
        text = text.replace("  livox_ros_driver\n", "  livox_ros_driver2\n")
    elif "  livox_ros_driver2\n" not in text:
        raise RuntimeError(f"neither livox_ros_driver nor livox_ros_driver2 found in {cmake}")
    cmake.write_text(text, encoding="utf-8")
    text = package.read_text(encoding="utf-8")
    text = text.replace("<build_depend>livox_ros_driver</build_depend>", "<build_depend>livox_ros_driver2</build_depend>")
    text = text.replace("<run_depend>livox_ros_driver</run_depend>", "<run_depend>livox_ros_driver2</run_depend>")
    package.write_text(text, encoding="utf-8")


def adapt_cmake_sophus_finder() -> None:
    cmake = ROOT / "CMakeLists.txt"
    module_dir = ROOT / "CMakeModules"
    module_dir.mkdir(exist_ok=True)
    write(
        module_dir / "FindSophus.cmake",
        """# RK3588 local Sophus finder for FAST-LIVO.
find_path(Sophus_INCLUDE_DIRS
  NAMES sophus/se3.hpp sophus/se3.h
  PATHS /usr/local/include /usr/include
)
find_library(Sophus_LIBRARIES
  NAMES Sophus sophus
  PATHS /usr/local/lib /usr/lib /usr/lib/aarch64-linux-gnu
)
include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Sophus DEFAULT_MSG Sophus_INCLUDE_DIRS Sophus_LIBRARIES)
mark_as_advanced(Sophus_INCLUDE_DIRS Sophus_LIBRARIES)
""",
    )

    text = cmake.read_text(encoding="utf-8")
    marker = "list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/CMakeModules)"
    if marker not in text:
        text = text.replace(
            "project(fast_livo)\n",
            "project(fast_livo)\n\n"
            "# Keep official FAST-LIVO logic intact; this only exposes local CMake finders.\n"
            f"{marker}\n",
            1,
        )

    libusb_marker = "find_library(LIBUSB_1_LIBRARY usb-1.0 REQUIRED)"
    if libusb_marker not in text:
        text = text.replace(
            "FIND_PACKAGE(Boost REQUIRED COMPONENTS thread)\n",
            "FIND_PACKAGE(Boost REQUIRED COMPONENTS thread)\n"
            "# RK3588 link compatibility for PCL/libusb symbol libusb_set_option.\n"
            f"{libusb_marker}\n",
            1,
        )

    old_link = "target_link_libraries(fastlivo_mapping ${catkin_LIBRARIES} ${PCL_LIBRARIES} ${PYTHON_LIBRARIES} vio ikdtree)"
    new_link = "target_link_libraries(fastlivo_mapping ${catkin_LIBRARIES} ${PCL_LIBRARIES} ${PYTHON_LIBRARIES} ${LIBUSB_1_LIBRARY} vio ikdtree)"
    if old_link in text:
        text = text.replace(old_link, new_link, 1)
    elif new_link not in text:
        raise RuntimeError(f"fastlivo_mapping target_link_libraries pattern not found in {cmake}")

    cmake.write_text(text, encoding="utf-8")


def adapt_preprocess_body() -> None:
    preprocess_cpp = ROOT / "src/preprocess.cpp"
    body = r'''void Preprocess::avia_handler(const livox_ros_driver2::CustomMsg::ConstPtr &msg)
{
  pl_surf.clear();
  pl_corn.clear();
  pl_full.clear();
  double t1 = omp_get_wtime();
  int plsize = msg->point_num;

  uint valid_num = 0;

  pl_corn.reserve(plsize);
  pl_surf.reserve(plsize);
  pl_full.resize(plsize);

  for(int i=0; i<N_SCANS; i++)
  {
    pl_buff[i].clear();
    pl_buff[i].reserve(plsize);
  }

  if (feature_enabled)
  {
    for(uint i=1; i<plsize; i++)
    {
      if((msg->points[i].line < N_SCANS) && ((msg->points[i].tag & 0x30) == 0x10 || (msg->points[i].tag & 0x30) == 0x00))
      {
        pl_full[i].x = msg->points[i].x;
        pl_full[i].y = msg->points[i].y;
        pl_full[i].z = msg->points[i].z;
        pl_full[i].intensity = msg->points[i].reflectivity;
        pl_full[i].curvature = msg->points[i].offset_time / float(1000000);

        if((abs(pl_full[i].x - pl_full[i-1].x) > 1e-7)
            || (abs(pl_full[i].y - pl_full[i-1].y) > 1e-7)
            || (abs(pl_full[i].z - pl_full[i-1].z) > 1e-7))
        {
          pl_buff[msg->points[i].line].push_back(pl_full[i]);
        }
      }
    }
    static int count = 0;
    static double time = 0.0;
    count ++;
    double t0 = omp_get_wtime();
    for(int j=0; j<N_SCANS; j++)
    {
      if(pl_buff[j].size() <= 5) continue;
      pcl::PointCloud<PointType> &pl = pl_buff[j];
      plsize = pl.size();
      vector<orgtype> &types = typess[j];
      types.clear();
      types.resize(plsize);
      plsize--;
      for(uint i=0; i<plsize; i++)
      {
        types[i].range = sqrt(pl[i].x * pl[i].x + pl[i].y * pl[i].y);
        vx = pl[i].x - pl[i + 1].x;
        vy = pl[i].y - pl[i + 1].y;
        vz = pl[i].z - pl[i + 1].z;
        types[i].dista = sqrt(vx * vx + vy * vy + vz * vz);
      }
      types[plsize].range = sqrt(pl[plsize].x * pl[plsize].x + pl[plsize].y * pl[plsize].y);
      give_feature(pl, types);
    }
    time += omp_get_wtime() - t0;
    printf("Feature extraction time: %lf \n", time / count);
  }
  else
  {
    for(uint i=1; i<plsize; i++)
    {
      if((msg->points[i].line < N_SCANS) && ((msg->points[i].tag & 0x30) == 0x10 || (msg->points[i].tag & 0x30) == 0x00))
      {
        valid_num ++;
        if (valid_num % point_filter_num == 0)
        {
          pl_full[i].x = msg->points[i].x;
          pl_full[i].y = msg->points[i].y;
          pl_full[i].z = msg->points[i].z;
          pl_full[i].intensity = msg->points[i].reflectivity;
          pl_full[i].curvature = msg->points[i].offset_time / float(1000000);

          if(((abs(pl_full[i].x - pl_full[i-1].x) > 1e-7)
              || (abs(pl_full[i].y - pl_full[i-1].y) > 1e-7)
              || (abs(pl_full[i].z - pl_full[i-1].z) > 1e-7))
              && (pl_full[i].x * pl_full[i].x + pl_full[i].y * pl_full[i].y + pl_full[i].z * pl_full[i].z > (blind * blind)))
          {
            pl_surf.push_back(pl_full[i]);
          }
        }
      }
    }
  }
  printf("feature extraction time: %lf \n", omp_get_wtime()-t1);
}'''
    replace_between(
        preprocess_cpp,
        "void Preprocess::avia_handler(const livox_ros_driver2::CustomMsg::ConstPtr &msg)",
        "void Preprocess::oust64_handler",
        body,
    )


def write_project_configs() -> None:
    write(
        ROOT / "config/camera_pinhole_hk.yaml",
        """cam_model: Pinhole
cam_width: 1440
cam_height: 1080
scale: 0.5
cam_fx: 1363.99324
cam_fy: 1362.70434
cam_cx: 710.95104
cam_cy: 569.24445
cam_d0: -0.136245
cam_d1: 0.132247
cam_d2: -0.000207
cam_d3: 0.001075
""",
    )
    write(
        ROOT / "config/mid360.yaml",
        """feature_extract_enable: 0
point_filter_num: 2
max_iteration: 3
dense_map_enable: 1
filter_size_surf: 0.5
filter_size_map: 0.3
cube_side_length: 1000
debug: 0
grid_size: 40
patch_size: 8
img_enable: 1
lidar_enable: 1
outlier_threshold: 300
ncc_en: false
ncc_thre: 0
img_point_cov: 100
laser_point_cov: 0.001
cam_fx: 1363.99324
cam_fy: 1362.70434
cam_cx: 710.95104
cam_cy: 569.24445
pose_output_en: false
delta_time: 0.0

common:
    lid_topic: "/livox/lidar"
    imu_topic: "/livox/imu"

preprocess:
    lidar_type: 1
    scan_line: 4
    blind: 0.5

mapping:
    acc_cov_scale: 100
    gyr_cov_scale: 10000
    fov_degree: 120
    det_range: 100.0
    extrinsic_est_en: false
    extrinsic_T: [-0.011, -0.02329, 0.04412]
    extrinsic_R: [1, 0, 0,
                  0, 1, 0,
                  0, 0, 1]

pcd_save:
    pcd_save_en: false

camera:
    img_topic: /hikrobot_camera/rgb
    Rcl: [0.001521317694, 0.416612140501, 0.909083060001,
          -0.999976761951, 0.00667500765, -0.001385579535,
          -0.006645385636, -0.909059826777, 0.416612614055]
    Pcl: [0.073348003893, -0.023326850681, -0.193087298136]
""",
    )
    write(
        ROOT / "launch/mapping_mid360.launch",
        """<launch>
  <!-- RK3588 Mid-360 + Hikrobot ROS1 FAST-LIVO mapping.
       Follows the local tutorial's mapping_mid360.launch structure.
       Sensor drivers are started separately by the project capture launch. -->
  <arg name="rviz" default="true" />

  <rosparam command="load" file="$(find fast_livo)/config/mid360.yaml" />

  <node launch-prefix="env LD_PRELOAD=/lib/aarch64-linux-gnu/libusb-1.0.so.0" pkg="fast_livo" type="fastlivo_mapping" name="laserMapping" output="screen">
    <rosparam file="$(find fast_livo)/config/camera_pinhole_hk.yaml" />
  </node>

  <group if="$(arg rviz)">
    <node launch-prefix="nice" pkg="rviz" type="rviz" name="rviz" args="-d $(find fast_livo)/rviz_cfg/loam_livox.rviz" />
  </group>
</launch>
""",
    )


def main() -> None:
    adapt_driver2()
    adapt_cmake_sophus_finder()
    adapt_preprocess_body()
    write_project_configs()
    print("APPLIED_FAST_LIVO_MID360_TUTORIAL_ADAPT")


if __name__ == "__main__":
    main()
