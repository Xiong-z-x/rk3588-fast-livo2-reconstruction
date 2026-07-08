export type AdapterState = 'mock' | 'waiting' | 'live' | 'error'

export type RosTopicName =
  | '/map_colored'
  | '/map_colored_only'
  | '/map_uncolored'
  | '/livox/lidar'
  | '/livox/lidar_pointcloud2'
  | '/livox/imu'
  | '/cloud_registered'
  | '/Odometry'
  | '/path'
  | '/tf'
  | '/tf_static'

export type RosStatusSnapshot = {
  adapterState: AdapterState
  sourceLabel: string
  bridgeUrl: string
  primaryTopic: RosTopicName
  timestamp: string
  note: string
}
