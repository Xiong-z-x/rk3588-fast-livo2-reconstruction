cmake_minimum_required(VERSION 2.8.3)

project(hikrobot_camera)

add_compile_options(-std=c++11)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  rospy
  std_msgs
  cv_bridge
  image_transport
  camera_info_manager
)

catkin_package(
 
)

find_package(OpenCV 4.2.0 REQUIRED)

include_directories(
  ${catkin_INCLUDE_DIRS}
  ${OpenCV_INCLUDE_DIRS}
  include
  /opt/MVS/include/
)

LINK_DIRECTORIES(
/opt/MVS/lib/64/
)

add_executable(${PROJECT_NAME}
src/hikrobot_camera.cpp)

 target_link_libraries(${PROJECT_NAME}
   ${catkin_LIBRARIES}
   ${OpenCV_LIBRARIES}
   MvCameraControl
   MVGigEVisionSDK
   MVRender
   MvUsb3vTL
   MediaProcess
   X11
 )
