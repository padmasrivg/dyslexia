export type BBox = [number, number, number, number]

export interface ApiError { kind: string; message: string }
export interface Word { text: string; bbox: BBox; confidence: number; line_id: number }
export interface Timing { last_ms: number; avg_ms: number; max_ms: number; samples: number }
export interface AssistTimings {
  api_roundtrip_ms?: number
  apigw_overhead_ms?: number
  lambda_ms?: number
  bedrock_ms?: number
  polly_ms?: number
  total_assistance_ms?: number
}
export interface Assistance {
  id: number
  word: string
  context: string
  definition: string
  source: string
  has_audio: boolean
  audio_url: string | null
  bbox: BBox | null
  created_at: number
  expires_at: number
  active: boolean
  timings?: AssistTimings
}
export interface AgentEvent { id: number; t: number; name: string; detail: string }
export interface LogLine { t: number; level: string; message: string }

export interface AgentState {
  server_time: number
  running: boolean
  status: { state: string; label: string; error: ApiError | null; notice: ApiError | string | null }
  input: {
    mode: string
    simulation: boolean
    frame: { width: number; height: number }
    detector: string
    ocr: string
    focus_source: string
    cloud: string
    cloud_reason: string
    audio_player: boolean
  }
  config: {
    dwell_threshold_s: number
    cooldown_s: number
    overlay_seconds: number
    use_clahe: boolean
    use_adaptive_threshold: boolean
    min_ocr_confidence: number
  }
  words: Word[]
  regions: { bbox: BBox; confidence: number }[]
  sentences?: Array<{
    line_id: number
    text: string
    confidence?: number
    words: Array<{ text: string; confidence?: number; bbox?: BBox }>
  }>
  camera_flipped?: boolean
  focus: {
    word: string | null
    bbox: BBox | null
    dwell_s: number
    threshold_s: number
    progress: number
    in_cooldown: boolean
    point: [number, number] | null
  } | null
  assistance: Assistance | null
  last_request: { word: string; context: string; sent_at: number } | null
  metrics: {
    fps: number
    timings: Record<string, Timing>
    counters: Record<string, number>
  }
  events: AgentEvent[]
  log: LogLine[]
}

export interface ActionResult { ok: boolean; error?: ApiError }
export interface DeviceList {
  monitors: { index: number; left: number; top: number; width: number; height: number }[]
  cameras: { index: number }[]
  cameras_probed: boolean
}
