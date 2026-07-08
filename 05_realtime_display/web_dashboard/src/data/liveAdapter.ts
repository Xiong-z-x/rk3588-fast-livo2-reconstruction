import type { RosStatusSnapshot } from '../types'

const endpoint = import.meta.env.VITE_EDGE_STATUS_ENDPOINT ?? '/api/status'

export const waitingSnapshot: RosStatusSnapshot = {
  adapterState: 'waiting',
  sourceLabel: '等待端侧状态后端',
  bridgeUrl: 'ws://127.0.0.1:8765',
  primaryTopic: '/cloud_registered',
  timestamp: new Date(0).toISOString(),
  note: '启动 rk3588_edge_status_server.py 后，页面会从真实端侧接口刷新 ROS、Docker、CPU、内存和 RKNPU 状态。',
  host: '127.0.0.1',
  container: 'rk3588_dev',
  metrics: [
    { label: 'CPU 负载', value: '等待', unit: 'loadavg', status: 'waiting' },
    { label: '内存占用', value: '等待', unit: '%', status: 'waiting' },
    { label: 'RKNPU 负载', value: '等待', unit: '% / raw', status: 'waiting' },
    { label: 'ROS Master', value: '等待', unit: '11311', status: 'waiting' },
  ],
  topics: [
    { name: '/livox/lidar', type: 'livox_ros_driver2/CustomMsg', status: 'waiting' },
    { name: '/livox/imu', type: 'sensor_msgs/Imu', status: 'waiting' },
    { name: '/hikrobot_camera/rgb', type: 'sensor_msgs/Image', status: 'waiting' },
    { name: '/cloud_registered', type: 'sensor_msgs/PointCloud2', status: 'waiting' },
    { name: '/path', type: 'nav_msgs/Path', status: 'waiting' },
  ],
  pose: { source: '未接入' },
  events: [
    {
      time: '--',
      level: 'INFO',
      text: '页面本身不伪造实时指标；接口不可达时只显示等待或错误状态。',
    },
  ],
}

export async function fetchLiveSnapshot(signal?: AbortSignal): Promise<RosStatusSnapshot> {
  const response = await fetch(endpoint, {
    signal,
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`edge status endpoint returned HTTP ${response.status}`)
  }

  return (await response.json()) as RosStatusSnapshot
}
