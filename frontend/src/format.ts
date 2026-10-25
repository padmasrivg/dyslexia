export const fmtMs = (v: number | undefined | null): string =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(1)} ms` : 'no samples yet'

export const fmtS = (v: number | undefined | null): string =>
  typeof v === 'number' && isFinite(v) ? `${v.toFixed(1)} s` : 'not available'

export const fmtTime = (t: number): string => {
  const d = new Date(t * 1000)
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

export const MODE_LABEL: Record<string, string> = {
  screen: 'Screen',
  camera: 'Camera',
  demo: 'Demo simulation',
}

export const CLOUD_LABEL: Record<string, string> = {
  aws: 'AWS',
  mock: 'Mock',
  none: 'None',
  auto: 'Auto',
}

// Plain language explanations for error and notice kinds from the agent.
const KIND_TEXT: Record<string, string> = {
  low_confidence: 'The text under the focus was too unclear to read with confidence, so nothing was sent.',
  no_text: 'No text was found in the picture. Check that the source shows a page of text.',
  empty_text: 'The recognised text was empty, so there was nothing to explain.',
  timeout: 'The cloud did not answer in time. Try the word again.',
  network: 'This computer could not reach the cloud service. Check the network connection.',
  api_gateway: 'The cloud gateway refused or failed the request.',
  service_error: 'A cloud service reported an error while preparing the explanation.',
  audio_failed: 'The explanation arrived but the audio could not be played.',
  capture_failed: 'The agent could not capture the screen or camera picture.',
  camera_unavailable: 'The camera could not be opened. It may be in use by another program or not allowed.',
  not_running: 'The assistant is not running. Start it first.',
  demo_busy: 'A guided demo run is already in progress.',
  invalid_config: 'A setting was not a valid number or switch.',
  no_audio: 'There is no audio for the latest explanation.',
}

export const explainKind = (kind: string): string =>
  KIND_TEXT[kind] ?? 'The agent reported a problem.'

export const noticeToError = (n: unknown): { kind: string; message: string } | null => {
  if (!n) return null
  if (typeof n === 'string') return { kind: n, message: '' }
  const o = n as { kind?: string; message?: string }
  return { kind: o.kind ?? 'notice', message: o.message ?? '' }
}

export const TIMING_NAMES: [string, string][] = [
  ['frame_capture', 'Frame capture'],
  ['preprocess', 'OpenCV preprocessing'],
  ['text_detection', 'Text detection'],
  ['ocr', 'OCR'],
  ['focus_detection', 'Focus detection'],
  ['dwell_to_trigger', 'Dwell to trigger'],
  ['render', 'Render'],
  ['frame_total', 'Frame total'],
  ['api_roundtrip', 'API round trip'],
  ['apigw_overhead', 'API Gateway plus network overhead (derived)'],
  ['lambda_total', 'Lambda'],
  ['bedrock', 'Bedrock'],
  ['polly', 'Polly'],
  ['total_assistance', 'Total assistance'],
]

export const DEMO_STEPS: { name: string; label: string }[] = [
  { name: 'reading_started', label: 'Reading starts' },
  { name: 'text_detected', label: 'Text is detected' },
  { name: 'focus_started', label: 'Focus on difficult word' },
  { name: 'dwell_threshold_reached', label: 'Dwell timer reaches threshold' },
  { name: 'stuck_word', label: 'STUCK_WORD triggered' },
  { name: 'request_sent', label: 'Request sent to cloud' },
  { name: 'response_received', label: 'Explanation received' },
  { name: 'word_highlighted', label: 'Word highlighted' },
  { name: 'audio_played', label: 'Audio played' },
  { name: 'reading_resumed', label: 'Reading resumes' },
]
