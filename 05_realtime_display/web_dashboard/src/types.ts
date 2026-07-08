export type AdapterState = 'waiting' | 'live' | 'error'

export type StatusLevel = 'ready' | 'waiting' | 'warning' | 'offline'

export type TopicStatus = {
  name: string
  type: string
  hz?: number | null
  publishers?: number | null
  subscribers?: number | null
  status: StatusLevel
  message?: string
}

export type RuntimeMetric = {
  label: string
  value: string
  unit: string
  status: StatusLevel
}

export type PoseSnapshot = {
  source: string
  x?: number | null
  y?: number | null
  z?: number | null
  roll?: number | null
  pitch?: number | null
  yaw?: number | null
}

export type EventRecord = {
  time: string
  level: 'INFO' | 'WARN' | 'ERROR'
  text: string
}

export type RosStatusSnapshot = {
  adapterState: AdapterState
  sourceLabel: string
  bridgeUrl: string
  primaryTopic: string
  timestamp: string
  note: string
  host: string
  container: string
  metrics: RuntimeMetric[]
  topics: TopicStatus[]
  pose: PoseSnapshot
  events: EventRecord[]
}
