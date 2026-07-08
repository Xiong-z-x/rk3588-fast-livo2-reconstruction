# Camera Trigger and Timestamp Limits

The Hikrobot ROS driver exposes the external trigger settings through ROS parameters:

- `TriggerEnable`
- `TriggerMode`
- `TriggerSource`
- `LineSelector`

At startup, the driver prints the configured values before applying them through the Hikrobot MVS SDK. This is intended to make review and field debugging possible from logs.

For the project hardware, the STM32 trigger line should be verified against the Hikrobot MVS feature tree for the exact camera model. Numeric enum values such as `TriggerSource: 0` and `LineSelector: 0` are SDK/model-specific and must not be treated as universal constants without vendor documentation or MVS runtime inspection.

Current ROS image timestamps are assigned with `ros::Time::now()` when the image is published. This is not a strict hardware exposure timestamp. Therefore the technically correct claim is:

- STM32 external triggering controls camera exposure cadence.
- ROS timestamps support ROS-side approximate alignment and diagnostics.
- Strict synchronization claims require additional evidence, such as camera hardware timestamps, trigger sequence IDs, or measured synchronization error statistics.
