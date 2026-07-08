#include <iostream>
#include "opencv2/opencv.hpp"
#include <vector>
#include <ros/ros.h>
#include <cv_bridge/cv_bridge.h>
#include <image_transport/image_transport.h>
#include <sensor_msgs/CameraInfo.h>
#include <sensor_msgs/distortion_models.h>
#include <sensor_msgs/image_encodings.h>
#include "hikrobot_camera.hpp"

// 剪裁掉照片和雷达没有重合的视角，去除多余像素可以使rosbag包变小
#define FIT_LIDAR_CUT_IMAGE false
#if FIT_LIDAR_CUT_IMAGE
    #define FIT_min_x 420
    #define FIT_min_y 70
    #define FIT_max_x 2450
    #define FIT_max_y 2000
#endif 

using namespace std;
using namespace cv;

int main(int argc, char **argv)
{
    //********** variables    **********/
    cv::Mat src;
    //string src = "",image_pub = "";
    //********** rosnode init **********/
    ros::init(argc, argv, "hikrobot_camera");
    ros::NodeHandle hikrobot_camera;
    camera::Camera MVS_cap(hikrobot_camera);

    string topic_name;
    string camera_info_topic_name;
    string frame_id;
    int image_width;
    int image_height;
    double publish_rate_hz;
    vector<double> camera_matrix;
    vector<double> distortion_coefficients;
    vector<double> rectification_matrix;
    vector<double> projection_matrix;

    hikrobot_camera.param<string>("TopicName", topic_name, "/hikrobot_camera/rgb");
    hikrobot_camera.param<string>("CameraInfoTopicName", camera_info_topic_name, "/hikrobot_camera/camera_info");
    hikrobot_camera.param<string>("FrameId", frame_id, "hikrobot_camera");
    hikrobot_camera.param<int>("Width", image_width, 1440);
    hikrobot_camera.param<int>("width", image_width, image_width);
    hikrobot_camera.param<int>("Height", image_height, 1080);
    hikrobot_camera.param<int>("height", image_height, image_height);
    publish_rate_hz = camera::readNumericParam(hikrobot_camera, "FrameRate", 10.0);
    if (publish_rate_hz <= 0.0)
    {
        ROS_WARN_STREAM("FrameRate must be positive, got " << publish_rate_hz << "; using 10 Hz publish loop");
        publish_rate_hz = 10.0;
    }

    const vector<double> default_k = {1363.99324, 0.0, 710.95104,
                                      0.0, 1362.70434, 569.24445,
                                      0.0, 0.0, 1.0};
    const vector<double> default_d = {-0.136245, 0.132247, -0.000207, 0.001075, 0.0};
    const vector<double> default_r = {1.0, 0.0, 0.0,
                                      0.0, 1.0, 0.0,
                                      0.0, 0.0, 1.0};
    const vector<double> default_p = {1323.94861, 0.0, 711.47255, 0.0,
                                      0.0, 1335.89893, 569.50401, 0.0,
                                      0.0, 0.0, 1.0, 0.0};

    hikrobot_camera.param<vector<double>>("CameraMatrix", camera_matrix, default_k);
    hikrobot_camera.param<vector<double>>("DistortionCoefficients", distortion_coefficients, default_d);
    hikrobot_camera.param<vector<double>>("RectificationMatrix", rectification_matrix, default_r);
    hikrobot_camera.param<vector<double>>("ProjectionMatrix", projection_matrix, default_p);

    if (camera_matrix.size() != 9)
    {
        ROS_FATAL_STREAM("CameraMatrix must contain 9 values, got " << camera_matrix.size());
        return 2;
    }
    if (rectification_matrix.size() != 9)
    {
        ROS_FATAL_STREAM("RectificationMatrix must contain 9 values, got " << rectification_matrix.size());
        return 2;
    }
    if (projection_matrix.size() != 12)
    {
        ROS_FATAL_STREAM("ProjectionMatrix must contain 12 values, got " << projection_matrix.size());
        return 2;
    }

    //********** rosnode init **********/
    image_transport::ImageTransport main_cam_image(hikrobot_camera);
    image_transport::Publisher image_pub = main_cam_image.advertise(topic_name, 1000);
    ros::Publisher camera_info_pub = hikrobot_camera.advertise<sensor_msgs::CameraInfo>(camera_info_topic_name, 1000);

    sensor_msgs::Image image_msg;
    sensor_msgs::CameraInfo camera_info_msg;
    camera_info_msg.header.frame_id = frame_id;
    camera_info_msg.width = image_width;
    camera_info_msg.height = image_height;
    camera_info_msg.distortion_model = sensor_msgs::distortion_models::PLUMB_BOB;
    camera_info_msg.D = distortion_coefficients;
    for (size_t i = 0; i < camera_matrix.size(); ++i)
    {
        camera_info_msg.K[i] = camera_matrix[i];
        camera_info_msg.R[i] = rectification_matrix[i];
    }
    for (size_t i = 0; i < projection_matrix.size(); ++i)
    {
        camera_info_msg.P[i] = projection_matrix[i];
    }

    cv_bridge::CvImagePtr cv_ptr = boost::make_shared<cv_bridge::CvImage>();
    cv_ptr->encoding = sensor_msgs::image_encodings::RGB8;
    
    ros::Rate loop_rate(publish_rate_hz);

    while (ros::ok())
    {

        loop_rate.sleep();
        ros::spinOnce();

        MVS_cap.ReadImg(src);
        if (src.empty())
        {
            continue;
        }
#if FIT_LIDAR_CUT_IMAGE
        cv::Rect area(FIT_min_x,FIT_min_y,FIT_max_x-FIT_min_x,FIT_max_y-FIT_min_y); // cut区域：从左上角像素坐标x，y，宽，高
        cv::Mat src_new = src(area);
        cv_ptr->image = src_new;
#else
        cv_ptr->image = src;
#endif
        image_msg = *(cv_ptr->toImageMsg());
        image_msg.header.stamp = ros::Time::now();  // ros发出的时间不是快门时间
        image_msg.header.frame_id = frame_id;

        camera_info_msg.header.frame_id = image_msg.header.frame_id;
        camera_info_msg.width = image_msg.width;
        camera_info_msg.height = image_msg.height;
	    camera_info_msg.header.stamp = image_msg.header.stamp;
        image_pub.publish(image_msg);
        camera_info_pub.publish(camera_info_msg);

        //*******************************************************************************************************************/
    }
    return 0;
}
