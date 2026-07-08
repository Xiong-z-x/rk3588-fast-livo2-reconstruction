import { useState, type ReactNode } from 'react'
import {
  Activity,
  Box,
  Cpu,
  Database,
  Gauge,
  Layers,
  Map,
  Maximize2,
  Network,
  Play,
  Radar,
  RotateCcw,
  Terminal,
  Waypoints,
  Wifi,
} from 'lucide-react'
import { developmentSnapshot } from './data/mockAdapter'
import './App.css'

type Status = 'ready' | 'waiting' | 'warning' | 'offline'
type StageKey = 'overview' | 'map' | 'algorithms' | 'link'

type TopicItem = {
  topic: string
  type: string
  role: string
  source: string
  status: Status
}

type PipelineItem = {
  title: string
  detail: string
  status: Status
}

type Metric = {
  label: string
  value: string
  unit: string
  status: Status
}

const statusMeta: Record<Status, { label: string; className: string }> = {
  ready: { label: '上次确认', className: 'ready' },
  waiting: { label: '等待接入', className: 'waiting' },
  warning: { label: '需确认', className: 'warning' },
  offline: { label: '未运行', className: 'offline' },
}

const stages: Array<{
  key: StageKey
  label: string
  title: string
  desc: string
  icon: ReactNode
}> = [
  {
    key: 'overview',
    label: '展示总览',
    title: '任务态势总览',
    desc: '用于汇报时快速说明 RK3588、ROS1、Foxglove、网页展示层之间的关系。',
    icon: <Gauge size={20} />,
  },
  {
    key: 'map',
    label: '彩色地图',
    title: '三维点云地图展示',
    desc: '优先展示 /map_colored 或 /cloud_registered，保留原始 Livox 点云对比入口。',
    icon: <Map size={20} />,
  },
  {
    key: 'algorithms',
    label: '算法能力',
    title: '后续算法结果区',
    desc: '障碍物、区域、平面、路径和告警以 Marker、状态灯、统计卡片和日志呈现。',
    icon: <Box size={20} />,
  },
  {
    key: 'link',
    label: '接入链路',
    title: '只读数据接入链路',
    desc: '不重启、不修改组长 Docker/ROS 主线，只读取 Topic 并连接 Foxglove Bridge。',
    icon: <Network size={20} />,
  },
]

const pipeline: PipelineItem[] = [
  {
    title: 'RK3588 / LubanCat',
    detail: '固定 IP 192.168.x.x，SSH 目标 user@rk3588-board.local',
    status: 'ready',
  },
  {
    title: 'Docker 容器 rk3588_dev',
    detail: 'ROS1 Noetic，host network，工作区 /root/fast_lio2_ws',
    status: 'ready',
  },
  {
    title: 'ROS Topic 读取',
    detail: '只读检查 /map_colored、/livox/lidar、/tf 等数据',
    status: 'waiting',
  },
  {
    title: 'Foxglove Bridge',
    detail: '可用时连接 ws://192.168.x.x:8765',
    status: 'warning',
  },
  {
    title: 'Web Dashboard',
    detail: '低带宽状态、汇报面板、算法结果展示，不替代 Foxglove 点云主显示',
    status: 'waiting',
  },
]

const topics: TopicItem[] = [
  {
    topic: '/map_colored',
    type: 'sensor_msgs/PointCloud2',
    role: 'FAST-LIO2 彩色三维重建点云',
    source: '最新重建优先',
    status: 'waiting',
  },
  {
    topic: '/map_colored_only',
    type: 'sensor_msgs/PointCloud2',
    role: '仅彩色地图点云',
    source: '重建结果',
    status: 'waiting',
  },
  {
    topic: '/map_uncolored',
    type: 'sensor_msgs/PointCloud2',
    role: '无色地图点云',
    source: '调试对照',
    status: 'waiting',
  },
  {
    topic: '/livox/lidar',
    type: 'livox_ros_driver2/CustomMsg',
    role: 'Mid-360 原始雷达数据',
    source: 'Livox Driver',
    status: 'waiting',
  },
  {
    topic: '/cloud_registered',
    type: 'sensor_msgs/PointCloud2',
    role: 'FAST-LIO2 配准后点云',
    source: '建图主线',
    status: 'waiting',
  },
  {
    topic: '/Odometry',
    type: 'nav_msgs/Odometry',
    role: '当前位姿、速度和姿态',
    source: '状态面板',
    status: 'waiting',
  },
  {
    topic: '/path',
    type: 'nav_msgs/Path',
    role: '设备运动轨迹',
    source: '轨迹面板',
    status: 'waiting',
  },
  {
    topic: '/tf / /tf_static',
    type: 'tf2_msgs/TFMessage',
    role: '坐标系与 Frame Tree',
    source: '3D 坐标系',
    status: 'waiting',
  },
]

const metrics: Metric[] = [
  { label: '点云帧率', value: '等待', unit: 'Hz', status: 'waiting' },
  { label: '点云数量', value: '等待', unit: 'points/frame', status: 'waiting' },
  { label: '端到端延迟', value: '等待', unit: 'ms', status: 'waiting' },
  { label: '当前位姿', value: '未接入', unit: 'XYZ / RPY', status: 'waiting' },
]

const algorithmSlots = [
  { title: '障碍物检测', desc: 'Marker / Bounding Box / 告警 Topic', status: 'waiting' as Status },
  { title: '区域分割', desc: 'ROI 高亮 / 语义颜色 / 区域统计', status: 'waiting' as Status },
  { title: '地面与墙面识别', desc: '平面 Marker / 法向量 / 置信度', status: 'waiting' as Status },
  { title: '路径规划', desc: '候选路径 / 目标点 / 安全距离', status: 'waiting' as Status },
]

const events = [
  {
    time: '演示',
    level: 'INFO',
    text: '汇报演示模式只用于展示界面效果，中心点云为可视化预览，不作为实测结果。',
  },
  {
    time: '准备',
    level: 'INFO',
    text: '网页当前为展示层第二阶段设计预览，所有数值均标注为等待真实 ROS 数据。',
  },
  {
    time: '接入',
    level: 'INFO',
    text: '真实点云显示仍优先使用 Foxglove Web/Desktop，连接 ws://192.168.x.x:8765。',
  },
  {
    time: '边界',
    level: 'WARN',
    text: '只读进入 rk3588_dev 容器，不停止、不重启、不修改 Livox 或 FAST-LIO2 主线。',
  },
]

const poseRows = [
  ['X', '0.000 m'],
  ['Y', '0.000 m'],
  ['Z', '0.000 m'],
  ['Roll', '0.00 deg'],
  ['Pitch', '0.00 deg'],
  ['Yaw', '0.00 deg'],
]

const previewPoints = Array.from({ length: 220 }, (_, index) => ({
  id: index,
  left: 10 + ((index * 17) % 80),
  top: 12 + ((index * 29) % 72),
  size: index % 13 === 0 ? 4 : index % 5 === 0 ? 3 : 2,
  tone: index % 9 === 0 ? 'warm' : index % 4 === 0 ? 'green' : index % 3 === 0 ? 'cyan' : 'blue',
  delay: `${(index % 18) * 90}ms`,
}))

const previewStructures = [
  { id: 1, left: 22, top: 26, width: 9, height: 25, tone: 'cyan' },
  { id: 2, left: 34, top: 18, width: 7, height: 32, tone: 'blue' },
  { id: 3, left: 48, top: 24, width: 12, height: 22, tone: 'green' },
  { id: 4, left: 64, top: 20, width: 8, height: 30, tone: 'blue' },
  { id: 5, left: 72, top: 32, width: 11, height: 20, tone: 'warm' },
  { id: 6, left: 28, top: 58, width: 18, height: 8, tone: 'green' },
  { id: 7, left: 58, top: 60, width: 22, height: 7, tone: 'cyan' },
]

function StatusBadge({ status }: { status: Status }) {
  const meta = statusMeta[status]

  return (
    <span className={`status-badge ${meta.className}`}>
      <span className="status-dot" aria-hidden="true" />
      {meta.label}
    </span>
  )
}

function SectionTitle({
  icon,
  title,
  caption,
}: {
  icon: ReactNode
  title: string
  caption?: string
}) {
  return (
    <div className="section-title">
      <span className="section-icon">{icon}</span>
      <div>
        <h2>{title}</h2>
        {caption ? <p>{caption}</p> : null}
      </div>
    </div>
  )
}

function PipelineCard({ item }: { item: PipelineItem }) {
  return (
    <article className="pipeline-card">
      <div className="pipeline-node" aria-hidden="true" />
      <div>
        <div className="row-between">
          <strong>{item.title}</strong>
          <StatusBadge status={item.status} />
        </div>
        <p>{item.detail}</p>
      </div>
    </article>
  )
}

function TopicRow({ item }: { item: TopicItem }) {
  return (
    <article className="topic-row">
      <div>
        <strong translate="no">{item.topic}</strong>
        <p>
          <span translate="no">{item.type}</span> · {item.role}
        </p>
      </div>
      <span>{item.source}</span>
    </article>
  )
}

function MetricCard({ metric }: { metric: Metric }) {
  return (
    <article className="metric-card">
      <div className="row-between">
        <span>{metric.label}</span>
        <StatusBadge status={metric.status} />
      </div>
      <strong>{metric.value}</strong>
      <small>{metric.unit}</small>
    </article>
  )
}

function StageInsight({ activeStage }: { activeStage: StageKey }) {
  const stage = stages.find((item) => item.key === activeStage) ?? stages[0]

  if (activeStage === 'algorithms') {
    return (
      <div className="stage-insight algorithm-insight">
        {algorithmSlots.map((slot) => (
          <article key={slot.title}>
            <StatusBadge status={slot.status} />
            <strong>{slot.title}</strong>
            <span>{slot.desc}</span>
          </article>
        ))}
      </div>
    )
  }

  if (activeStage === 'link') {
    return (
      <div className="stage-insight link-insight">
        <div>
          <span>SSH</span>
          <strong translate="no">user@192.168.x.x</strong>
        </div>
        <div>
          <span>Container</span>
          <strong translate="no">docker exec rk3588_dev</strong>
        </div>
        <div>
          <span>Bridge</span>
          <strong translate="no">ws://192.168.x.x:8765</strong>
        </div>
      </div>
    )
  }

  return (
    <div className="stage-insight">
      <strong>{stage.title}</strong>
      <p>{stage.desc}</p>
      <div className="insight-tags">
        <span>Live / Stale 明确区分</span>
        <span>Foxglove 点云优先</span>
        <span>网页状态低带宽接入</span>
      </div>
    </div>
  )
}

function SceneViewport({
  activeStage,
  presentationMode,
  onTogglePresentationMode,
}: {
  activeStage: StageKey
  presentationMode: boolean
  onTogglePresentationMode: () => void
}) {
  const focusTopic =
    activeStage === 'map'
      ? '/map_colored'
      : activeStage === 'link'
        ? '/tf'
        : activeStage === 'algorithms'
          ? '/ui/markers'
          : developmentSnapshot.primaryTopic

  return (
    <section className="scene-card" aria-label="三维点云与轨迹主窗口">
      <div className="scene-toolbar">
        <div>
          <h2>三维点云地图 / 场景视图</h2>
          <p>
            当前焦点 <span translate="no">{focusTopic}</span>，真实显示以 Foxglove Bridge 数据为准
          </p>
        </div>
        <div className="scene-actions" aria-label="视图工具">
          <button
            className={presentationMode ? 'wide-action active' : 'wide-action'}
            type="button"
            onClick={onTogglePresentationMode}
          >
            {presentationMode ? '汇报演示' : '真实等待'}
          </button>
          <button type="button" aria-label="播放预览">
            <Play size={16} />
          </button>
          <button type="button" aria-label="重置视角">
            <RotateCcw size={16} />
          </button>
          <button type="button" aria-label="最大化视图">
            <Maximize2 size={16} />
          </button>
        </div>
      </div>

      <div className={presentationMode ? 'scene-canvas presentation-mode' : 'scene-canvas'}>
        <div className="scan-beam" aria-hidden="true" />
        <div className="orbit-ring ring-a" aria-hidden="true" />
        <div className="orbit-ring ring-b" aria-hidden="true" />
        <div className="orbit-ring ring-c" aria-hidden="true" />

        <svg className="scene-grid" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <pattern id="grid-lines" width="8" height="8" patternUnits="userSpaceOnUse">
              <path d="M 8 0 L 0 0 0 8" fill="none" stroke="rgba(37, 99, 235, 0.12)" strokeWidth="0.35" />
            </pattern>
          </defs>
          <rect width="100" height="100" fill="url(#grid-lines)" />
          <path className="scan-sector" d="M50 82 L17 26 Q50 3 84 26 Z" />
          <path className="route-path" d="M18 68 C30 58 38 63 46 50 C55 35 62 43 72 30 C78 22 84 24 90 18" />
          <path className="axis axis-x" d="M50 82 L78 70" />
          <path className="axis axis-y" d="M50 82 L42 56" />
          <path className="axis axis-z" d="M50 82 L50 48" />
        </svg>

        {previewPoints.map((point) => (
          <span
            className={`cloud-point ${point.tone}`}
            key={point.id}
            style={{
              left: `${point.left}%`,
              top: `${point.top}%`,
              width: point.size,
              height: point.size,
              animationDelay: point.delay,
            }}
          />
        ))}

        {previewStructures.map((item) => (
          <span
            className={`structure-block ${item.tone}`}
            key={item.id}
            style={{
              left: `${item.left}%`,
              top: `${item.top}%`,
              width: `${item.width}%`,
              height: `${item.height}%`,
            }}
          />
        ))}

        <div className="viewport-tools">
          <span>Fixed frame: map</span>
          <span>Display frame: livox_frame</span>
          <span>Decay: live / bag controlled</span>
        </div>

        <div className="mission-overlay">
          <span>第二阶段展示目标</span>
          <strong>真实点云由 Foxglove 承载，网页负责状态、轨迹、算法结果与汇报叙事。</strong>
        </div>

        <div className="height-legend">
          <strong>点云高度 m</strong>
          <div />
          <span>-10</span>
          <span>0</span>
          <span>15</span>
          <span>30</span>
        </div>

        {presentationMode ? (
          <div className="demo-disclaimer">
            <strong>汇报演示模式</strong>
            <span>中心点云为界面预览，不代表实测数据</span>
          </div>
        ) : (
          <div className="scene-notice">
            <Radar size={28} />
            <strong>等待实时 ROS 数据</strong>
            <span>当前为高级展示模板；真实点云打开 Foxglove 链接后由 RK3588 Bridge 提供。</span>
            <code translate="no">ws://192.168.x.x:8765</code>
          </div>
        )}
      </div>
    </section>
  )
}

function RightRail({ activeStage }: { activeStage: StageKey }) {
  return (
    <aside className="right-rail">
      <section className="panel-block">
        <SectionTitle icon={<Waypoints size={17} />} title="实时位姿 Odometry" caption="等待 /Odometry 接入" />
        <div className="pose-grid">
          {poseRows.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="metric-grid">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </section>

      <section className="panel-block compact">
        <SectionTitle icon={<Cpu size={17} />} title="系统运行状态" caption="低带宽状态 Topic 预留" />
        <div className="system-list">
          <div>
            <span>容器</span>
            <strong translate="no">rk3588_dev</strong>
          </div>
          <div>
            <span>网络</span>
            <strong>host / 只读</strong>
          </div>
          <div>
            <span>建图</span>
            <strong>{activeStage === 'map' ? '等待地图数据' : '未接入'}</strong>
          </div>
        </div>
      </section>
    </aside>
  )
}

function EventLog() {
  return (
    <section className="event-log" aria-label="日志或提示信息区域">
      <div className="row-between">
        <SectionTitle icon={<Terminal size={17} />} title="事件日志 / 提示信息" />
        <div className="log-filters" aria-label="日志筛选">
          <span>全部</span>
          <span>INFO</span>
          <span>WARN</span>
        </div>
      </div>
      <div className="log-rows">
        {events.map((event) => (
          <article key={`${event.time}-${event.text}`}>
            <span>{event.time}</span>
            <strong>{event.level}</strong>
            <p>{event.text}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

export default function App() {
  const [activeStage, setActiveStage] = useState<StageKey>('overview')
  const [presentationMode, setPresentationMode] = useState(true)
  const currentStage = stages.find((stage) => stage.key === activeStage) ?? stages[0]

  return (
    <main className="app-shell">
      <header className="mission-header">
        <div className="brand-cluster">
          <div className="brand-mark" aria-hidden="true">
            <Radar size={28} />
          </div>
          <div>
            <span>平台</span>
            <strong>RK3588 / LubanCat</strong>
          </div>
        </div>

        <div className="title-cluster">
          <h1>RK3588 三维感知展示中枢</h1>
          <p>Livox Mid-360 LiDAR · ROS1 · Foxglove · FAST-LIO2 结果展示预留</p>
          <div className="mission-tags" aria-label="展示重点">
            <span>原始点云</span>
            <span>彩色重建</span>
            <span>位姿轨迹</span>
            <span>算法结果</span>
          </div>
        </div>

        <div className="header-status" aria-label="连接状态">
          <span>
            <Wifi size={15} />
            固定 IP <b translate="no">192.168.x.x</b>
          </span>
          <span>
            <Database size={15} />
            数据状态：等待 live ROS
          </span>
        </div>
      </header>

      <section className="dashboard-layout">
        <aside className="left-rail">
          <section className="panel-block pipeline-block">
            <SectionTitle icon={<Activity size={17} />} title="数据接入链路" caption="从板端到展示层的只读路径" />
            <div className="pipeline-list">
              {pipeline.map((item) => (
                <PipelineCard key={item.title} item={item} />
              ))}
            </div>
          </section>

          <section className="panel-block topic-block">
            <SectionTitle icon={<Layers size={17} />} title="Topic 映射" caption="同一套 UI 逻辑兼容原始点云与重建点云" />
            <div className="topic-list">
              {topics.map((topic) => (
                <TopicRow key={topic.topic} item={topic} />
              ))}
            </div>
          </section>
        </aside>

        <section className="center-stage">
          <SceneViewport
            activeStage={activeStage}
            presentationMode={presentationMode}
            onTogglePresentationMode={() => setPresentationMode((value) => !value)}
          />
          <div className="center-bottom">
            <StageInsight activeStage={activeStage} />
            <EventLog />
          </div>
        </section>

        <RightRail activeStage={activeStage} />
      </section>

      <nav className="stage-switcher" aria-label="展示面板切换">
        {stages.map((stage) => (
          <button
            type="button"
            key={stage.key}
            className={activeStage === stage.key ? 'selected' : ''}
            onClick={() => setActiveStage(stage.key)}
            aria-current={activeStage === stage.key ? 'page' : undefined}
          >
            {stage.icon}
            <span>{stage.label}</span>
            <small>{stage.desc}</small>
          </button>
        ))}
      </nav>

      <div className="mission-watermark" aria-hidden="true">
        {currentStage.title}
      </div>
    </main>
  )
}
