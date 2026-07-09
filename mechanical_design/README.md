# Mechanical Design Sources

This directory stores the mechanical design source files used by the project.

## Handheld Kit

`handheld_kit/` contains the SolidWorks assembly and part files for the handheld data-acquisition structure. The fixture holds the Livox Mid-360 LiDAR, Hikrobot industrial camera and ELF2/RK3588-class board on one rigid frame for indoor calibration, rosbag recording and reconstruction tests.

Included files:

| File | Description |
| --- | --- |
| `handheld_kit/手持件.SLDASM` | SolidWorks assembly for the handheld acquisition kit |
| `handheld_kit/雷达底件.SLDPRT` | LiDAR mounting base |
| `handheld_kit/相机底座固定.SLDPRT` | Camera mounting fixture |
| `handheld_kit/顶层.SLDPRT` | Upper support plate |
| `handheld_kit/底层.SLDPRT` | Lower support plate |
| `handheld_kit/铝柱50mm.SLDPRT` | 50 mm aluminum spacer column |

## UAV Platform

`uav_platform/` is reserved for the UAV mechanical source package. During the current repository import, the local source directory `D:\无人机` only contained SolidWorks temporary lock files and zero-byte placeholders, so no valid UAV SolidWorks source file was committed from that directory. The UAV hardware images and demonstration videos are stored under `media/`.
