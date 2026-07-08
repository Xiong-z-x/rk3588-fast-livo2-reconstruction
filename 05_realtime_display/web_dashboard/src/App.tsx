import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Activity,
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
import { fetchLiveSnapshot, waitingSnapshot } from './data/liveAdapter'
import type { EventRecord, RosStatusSnapshot, RuntimeMetric, StatusLevel, TopicStatus } from './types'
import './App.css'

type StageKey = 'overview' | 'map' | 'runtime' | 'link'

const statusMeta: Record<StatusLevel, { label: string; className: string }> = {
  ready: { label: '正常', className: 'ready' },
  waiting: { label: '等待', className: 'waiting' },
  warning: { label: '告警', className: 'warning' },
  offline: { label: '离线', className: 'offline' },
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
    label: '总览',
    title: '端侧建图状态总览',
    desc: '汇总 ROS、Docker、传感器 topic 与端侧资源。',
    icon: <Gauge size={20} />,
  },
  {
    key: 'map',
    label: '点云',
    title: 'FAST-LIVO2 点云链路',
    desc: '优先检查 /cloud_registered、/path 与 WebGL/Foxglove 展示入口。',
    icon: <Map size={20} />,
  },
  {
    key: 'runtime',
    label: '端侧',
    title: 'RK3588 运行资源',
    desc: '读取 CPU、内存、RKNPU debugfs、Docker 与 ROS Master 状态。',
    icon: <Cpu size={20} />,
  },
  {
    key: 'link',
    label: '接入',
    title: '只读接入链路',
    desc: '默认只读采集状态；Foxglove bridge 默认绑定 127.0.0.1。',
    icon: <Network size={20} />,
  },
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

function formatNumber(value?: number | null, digits = 3): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '等待'
}

function StatusBadge({ status }: { status: StatusLevel }) {
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

function PipelineCard({
  title,
  detail,
  status,
}: {
  title: string
  detail: string
  status: StatusLevel
}) {
  return (
    <article className="pipeline-card">
      <div className="pipeline-node" aria-hidden="true" />
      <div>
        <div className="row-between">
          <strong>{title}</strong>
          <StatusBadge status={status} />
        </div>
        <p>{detail}</p>
      </div>
    </article>
  )
}

function TopicRow({ item }: { item: TopicStatus }) {
  const hzText = typeof item.hz === 'number' ? `${item.hz.toFixed(2)} Hz` : '未测频率'

  return (
    <article className="topic-row">
      <div>
        <strong translate="no">{item.name}</strong>
        <p>
          <span translate="no">{item.type || 'unknown'}</span> / {hzText}
        </p>
      </div>
      <StatusBadge status={item.status} />
    </article>
  )
}

function MetricCard({ metric }: { metric: RuntimeMetric }) {
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

function StageInsight({ activeStage, snapshot }: { activeStage: StageKey; snapshot: RosStatusSnapshot }) {
  if (activeStage === 'runtime') {
    return (
      <div className="stage-insight algorithm-insight">
        {snapshot.metrics.map((metric) => (
          <article key={metric.label}>
            <StatusBadge status={metric.status} />
            <strong>{metric.label}</strong>
            <span>
              {metric.value} {metric.unit}
            </span>
          </article>
        ))}
      </div>
    )
  }

  if (activeStage === 'link') {
    return (
      <div className="stage-insight link-insight">
        <div>
          <span>Host</span>
          <strong translate="no">{snapshot.host}</strong>
        </div>
        <div>
          <span>Container</span>
          <strong translate="no">{snapshot.container}</strong>
        </div>
        <div>
          <span>Bridge</span>
          <strong translate="no">{snapshot.bridgeUrl}</strong>
        </div>
      </div>
    )
  }

  return (
    <div className="stage-insight">
      <strong>{activeStage === 'map' ? '建图输出检查' : '系统状态来源'}</strong>
      <p>{snapshot.note}</p>
      <div className="insight-tags">
        <span>{snapshot.adapterState === 'live' ? '真实端侧数据' : '接口未接入'}</span>
        <span>ROS1 Noetic</span>
        <span>FAST-LIVO2 / ONLY_LIO</span>
      </div>
    </div>
  )
}

function SceneViewport({
  snapshot,
  activeStage,
  presentationMode,
  onTogglePresentationMode,
}: {
  snapshot: RosStatusSnapshot
  activeStage: StageKey
  presentationMode: boolean
  onTogglePresentationMode: () => void
}) {
  const focusTopic =
    activeStage === 'map'
      ? '/cloud_registered'
      : activeStage === 'link'
        ? '/tf'
        : activeStage === 'runtime'
          ? '/diagnostics'
          : snapshot.primaryTopic

  return (
    <section className="scene-card" aria-label="点云与端侧状态主窗口">
      <div className="scene-toolbar">
        <div>
          <h2>三维建图链路 / 端侧状态</h2>
          <p>
            当前焦点 <span translate="no">{focusTopic}</span>，页面状态来自 <span translate="no">/api/status</span>
          </p>
        </div>
        <div className="scene-actions" aria-label="视图工具">
          <button className={presentationMode ? 'wide-action active' : 'wide-action'} type="button" onClick={onTogglePresentationMode}>
            {presentationMode ? '状态图' : '等待图'}
          </button>
          <button type="button" aria-label="播放预览">
            <Play size={16} />
          </button>
          <button type="button" aria-label="重置视角">
            <RotateCcw size={16} />
          </button>
          <button type="button" aria-label="最大化">
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
          <span>Primary: {snapshot.primaryTopic}</span>
          <span>Updated: {snapshot.timestamp}</span>
        </div>

        <div className="mission-overlay">
          <span>{snapshot.sourceLabel}</span>
          <strong>{snapshot.adapterState === 'live' ? '当前页面正在显示端侧真实状态接口返回值。' : '未连接真实接口时不展示伪造实时指标。'}</strong>
        </div>

        <div className="height-legend">
          <strong>状态</strong>
          <div />
          <span>offline</span>
          <span>wait</span>
          <span>live</span>
        </div>

        {snapshot.adapterState !== 'live' ? (
          <div className="scene-notice">
            <Radar size={28} />
            <strong>等待端侧接口</strong>
            <span>{snapshot.note}</span>
            <code translate="no">python3 rk3588_edge_status_server.py --host 127.0.0.1 --port 8766</code>
          </div>
        ) : null}
      </div>
    </section>
  )
}

function RightRail({ snapshot }: { snapshot: RosStatusSnapshot }) {
  const poseRows = [
    ['X', `${formatNumber(snapshot.pose.x)} m`],
    ['Y', `${formatNumber(snapshot.pose.y)} m`],
    ['Z', `${formatNumber(snapshot.pose.z)} m`],
    ['Roll', `${formatNumber(snapshot.pose.roll, 2)} deg`],
    ['Pitch', `${formatNumber(snapshot.pose.pitch, 2)} deg`],
    ['Yaw', `${formatNumber(snapshot.pose.yaw, 2)} deg`],
  ]

  return (
    <aside className="right-rail">
      <section className="panel-block">
        <SectionTitle icon={<Waypoints size={17} />} title="位姿 Odometry" caption={snapshot.pose.source} />
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
        {snapshot.metrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </section>

      <section className="panel-block compact">
        <SectionTitle icon={<Cpu size={17} />} title="运行对象" caption="来自端侧状态接口" />
        <div className="system-list">
          <div>
            <span>主机</span>
            <strong translate="no">{snapshot.host}</strong>
          </div>
          <div>
            <span>容器</span>
            <strong translate="no">{snapshot.container}</strong>
          </div>
          <div>
            <span>Bridge</span>
            <strong translate="no">{snapshot.bridgeUrl}</strong>
          </div>
        </div>
      </section>
    </aside>
  )
}

function EventLog({ events }: { events: EventRecord[] }) {
  return (
    <section className="event-log" aria-label="事件日志">
      <div className="row-between">
        <SectionTitle icon={<Terminal size={17} />} title="事件日志" />
        <div className="log-filters" aria-label="日志级别">
          <span>LIVE</span>
          <span>ROS</span>
          <span>EDGE</span>
        </div>
      </div>
      <div className="log-rows">
        {events.map((event, index) => (
          <article key={`${event.time}-${event.level}-${index}`}>
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
  const [snapshot, setSnapshot] = useState<RosStatusSnapshot>(waitingSnapshot)
  const currentStage = stages.find((stage) => stage.key === activeStage) ?? stages[0]

  useEffect(() => {
    let active = true
    const controller = new AbortController()

    async function refresh() {
      try {
        const next = await fetchLiveSnapshot(controller.signal)
        if (active) {
          setSnapshot(next)
        }
      } catch (error) {
        if (active) {
          const message = error instanceof Error ? error.message : String(error)
          setSnapshot({
            ...waitingSnapshot,
            adapterState: 'error',
            sourceLabel: '端侧状态接口不可达',
            timestamp: new Date().toISOString(),
            note: message,
            events: [
              {
                time: new Date().toLocaleTimeString(),
                level: 'ERROR',
                text: message,
              },
            ],
          })
        }
      }
    }

    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, 2500)

    return () => {
      active = false
      controller.abort()
      window.clearInterval(timer)
    }
  }, [])

  const pipeline = useMemo(
    () => [
      {
        title: '端侧后端',
        detail: snapshot.sourceLabel,
        status: snapshot.adapterState === 'live' ? 'ready' : snapshot.adapterState === 'error' ? 'warning' : 'waiting',
      },
      {
        title: 'Docker / ROS1',
        detail: `${snapshot.container} / ${snapshot.host}`,
        status: snapshot.topics.some((topic) => topic.status === 'ready') ? 'ready' : 'waiting',
      },
      {
        title: 'FAST-LIVO2 输出',
        detail: snapshot.primaryTopic,
        status: snapshot.topics.find((topic) => topic.name === snapshot.primaryTopic)?.status ?? 'waiting',
      },
      {
        title: 'Foxglove Bridge',
        detail: snapshot.bridgeUrl,
        status: snapshot.bridgeUrl.includes('127.0.0.1') ? 'ready' : 'warning',
      },
    ],
    [snapshot],
  )

  return (
    <main className="app-shell">
      <header className="mission-header">
        <div className="brand-cluster">
          <div className="brand-mark" aria-hidden="true">
            <Radar size={28} />
          </div>
          <div>
            <span>平台</span>
            <strong>RK3588 / ELF2</strong>
          </div>
        </div>

        <div className="title-cluster">
          <h1>端侧三维重建状态面板</h1>
          <p>Livox Mid-360 / Hikrobot / FAST-LIVO2 / ROS1 Noetic</p>
          <div className="mission-tags" aria-label="显示重点">
            <span>真实接口</span>
            <span>ROS Topic</span>
            <span>位姿轨迹</span>
            <span>资源负载</span>
          </div>
        </div>

        <div className="header-status" aria-label="连接状态">
          <span>
            <Wifi size={15} />
            主机 <b translate="no">{snapshot.host}</b>
          </span>
          <span>
            <Database size={15} />
            数据状态：{statusMeta[snapshot.adapterState === 'live' ? 'ready' : snapshot.adapterState === 'error' ? 'warning' : 'waiting'].label}
          </span>
        </div>
      </header>

      <section className="dashboard-layout">
        <aside className="left-rail">
          <section className="panel-block pipeline-block">
            <SectionTitle icon={<Activity size={17} />} title="数据接入链路" caption="从端侧后端到网页的只读状态流" />
            <div className="pipeline-list">
              {pipeline.map((item) => (
                <PipelineCard key={item.title} title={item.title} detail={item.detail} status={item.status as StatusLevel} />
              ))}
            </div>
          </section>

          <section className="panel-block topic-block">
            <SectionTitle icon={<Layers size={17} />} title="ROS Topic" caption="后端通过 rostopic 读取真实类型与频率" />
            <div className="topic-list">
              {snapshot.topics.map((topic) => (
                <TopicRow key={topic.name} item={topic} />
              ))}
            </div>
          </section>
        </aside>

        <section className="center-stage">
          <SceneViewport
            snapshot={snapshot}
            activeStage={activeStage}
            presentationMode={presentationMode}
            onTogglePresentationMode={() => setPresentationMode((value) => !value)}
          />
          <div className="center-bottom">
            <StageInsight activeStage={activeStage} snapshot={snapshot} />
            <EventLog events={snapshot.events} />
          </div>
        </section>

        <RightRail snapshot={snapshot} />
      </section>

      <nav className="stage-switcher" aria-label="显示面板切换">
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
