export interface EdgeCargoResult {
  id: string;
  label: string;
  confidence: number;
  segmentation_score: number;
  center: [number, number, number];
  dimensions: [number, number, number];
  yaw: number;
  obb_volume_m3: number;
  occupied_volume_m3: number;
  occupancy_ratio: number;
  point_count: number;
}

export interface EdgeNpuLoad {
  core0: number;
  core1: number;
  core2: number;
  average: number;
  raw: string;
}

export interface SegmentRecognizeVolumeResponse {
  pcd_path: string;
  roi_point_count: number;
  cargos: EdgeCargoResult[];
  total_occupied_volume_m3: number;
  total_obb_volume_m3: number;
  npu_load: EdgeNpuLoad | null;
  timing_ms: Record<string, number>;
  feature_metadata: Record<string, unknown>;
}

export async function runEdgeAiSegmentRecognizeVolume(params: {
  pcdPath: string;
  bboxMin: [number, number, number];
  bboxMax: [number, number, number];
  readNpuLoad?: boolean;
}): Promise<SegmentRecognizeVolumeResponse> {
  const response = await fetch("/api/edge-ai/segment-recognize-volume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pcdPath: params.pcdPath,
      bboxMin: params.bboxMin,
      bboxMax: params.bboxMax,
      readNpuLoad: params.readNpuLoad ?? true,
    }),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Edge AI inference failed: ${response.status} ${message}`);
  }

  return (await response.json()) as SegmentRecognizeVolumeResponse;
}
