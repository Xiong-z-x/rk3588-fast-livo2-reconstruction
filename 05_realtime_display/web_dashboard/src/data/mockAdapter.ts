import type { RosStatusSnapshot } from '../types'

export const developmentSnapshot: RosStatusSnapshot = {
  adapterState: 'waiting',
  sourceLabel: '展示设计预览，等待真实 ROS 数据',
  bridgeUrl: 'ws://192.168.x.x:8765',
  primaryTopic: '/map_colored',
  timestamp: '等待 live ROS / rosbag 回放',
  note: '当前网页只负责展示层设计与低带宽状态承载；高密度真实点云第一阶段仍以 Foxglove 连接 RK3588 Bridge 为准。',
}
