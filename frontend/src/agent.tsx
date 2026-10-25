import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { AgentState, ApiError } from './types'
import { post } from './api'
import { DEMO_STEPS } from './format'

export interface Settings { mode: 'screen' | 'camera' | 'demo'; cloud: 'auto' | 'mock' | 'aws'; monitor: number; camera: number }

interface AgentCtx {
  state: AgentState | null
  reachable: boolean
  checking: boolean
  retry: () => void
  settings: Settings
  setSettings: (s: Partial<Settings>) => void
  busy: boolean
  actionError: ApiError | null
  clearActionError: () => void
  start: () => Promise<void>
  stop: () => Promise<void>
  runDemo: () => Promise<void>
  demoDone: Record<string, boolean>
  demoStarted: boolean
  demoMessage: string | null
}

const Ctx = createContext<AgentCtx | null>(null)
export const useAgent = () => {
  const c = useContext(Ctx)
  if (!c) throw new Error('AgentProvider missing')
  return c
}

// Reading and text detection belong to the running session, so they count even when the pipeline
// was already running before the guided demo button was pressed.
const SESSION_STEPS = new Set(['reading_started', 'text_detected'])

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

const INITIAL_STATE: AgentState = {
  server_time: Date.now() / 1000,
  running: false,
  status: { state: 'idle', label: 'Ready', error: null, notice: null },
  input: {
    mode: 'demo',
    simulation: false,
    frame: { width: 1280, height: 720 },
    detector: 'dbnet',
    ocr: 'rapid-ocr',
    focus_source: 'web_pointer',
    cloud: 'mock',
    cloud_reason: 'Local mode',
    audio_player: true,
  },
  config: {
    dwell_threshold_s: 1.2,
    cooldown_s: 2.0,
    overlay_seconds: 6.0,
    use_clahe: false,
    use_adaptive_threshold: false,
    min_ocr_confidence: 0.5,
  },
  words: [],
  regions: [],
  sentences: [],
  camera_flipped: false,
  focus: {
    word: null,
    bbox: null,
    dwell_s: 0,
    threshold_s: 1.2,
    progress: 0,
    in_cooldown: false,
    point: null,
  },
  assistance: null,
  last_request: null,
  metrics: { fps: 0, timings: {}, counters: {} },
  events: [],
  log: [],
}

async function fetchState(): Promise<AgentState> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), 3500)
  try {
    const r = await fetch('/api/state', { signal: ctl.signal, cache: 'no-store' })
    if (!r.ok) throw new Error(String(r.status))
    return (await r.json()) as AgentState
  } finally {
    clearTimeout(t)
  }
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AgentState | null>(INITIAL_STATE)
  const [reachable, setReachable] = useState(true)
  const [checking, setChecking] = useState(false)
  const [settings, setS] = useState<Settings>({ mode: 'demo', cloud: 'mock', monitor: 1, camera: 0 })
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [demoMessage, setDemoMessage] = useState<string | null>(null)
  const [demoCutoff, setDemoCutoff] = useState<number | null>(null)
  const [demoDone, setDemoDone] = useState<Record<string, boolean>>({})
  const latest = useRef<AgentState | null>(null)
  const fails = useRef(0)
  const wake = useRef<(() => void) | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      while (alive) {
        if (document.hidden) {
          await new Promise<void>((res) => { wake.current = res; setTimeout(res, 1000) })
          continue
        }
        try {
          const s = await fetchState()
          if (!alive) return
          fails.current = 0
          latest.current = s
          setState(s)
          setReachable(true)
        } catch {
          fails.current += 1
          if (fails.current >= 5 && alive) setReachable(false)
        }
        setChecking(false)
        await new Promise<void>((res) => { wake.current = res; setTimeout(res, 800) })
      }
    }
    const onVis = () => wake.current?.()
    document.addEventListener('visibilitychange', onVis)
    void tick()
    return () => { alive = false; document.removeEventListener('visibilitychange', onVis) }
  }, [])

  // Steps are Done once an event with that name appeared after the demo run began. Sticky, because
  // the agent keeps only the last 40 events.
  useEffect(() => {
    if (demoCutoff === null || !state) return
    setDemoDone((prev) => {
      let changed = false
      const next = { ...prev }
      for (const s of DEMO_STEPS) {
        if (!next[s.name] && state.events.some((e) => e.name === s.name && (e.t >= demoCutoff || SESSION_STEPS.has(s.name)))) {
          next[s.name] = true
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [state, demoCutoff])

  const retry = useCallback(() => { setChecking(true); fails.current = 0; wake.current?.() }, [])
  const setSettings = useCallback((s: Partial<Settings>) => setS((c) => ({ ...c, ...s })), [])

  const start = useCallback(async () => {
    setBusy(true); setActionError(null)
    const body: Record<string, unknown> = { mode: settings.mode, cloud: settings.cloud }
    if (settings.mode === 'screen') body.monitor = settings.monitor
    if (settings.mode === 'camera') body.camera = settings.camera
    const r = await post('/api/start', body)
    if (!r.ok) setActionError(r.error ?? { kind: 'service_error', message: 'Start failed.' })
    setBusy(false)
  }, [settings])

  const stop = useCallback(async () => {
    setBusy(true); setActionError(null)
    const r = await post('/api/stop')
    if (!r.ok) setActionError(r.error ?? { kind: 'service_error', message: 'Stop failed.' })
    setBusy(false)
  }, [])

  const runDemo = useCallback(async () => {
    setBusy(true); setActionError(null); setDemoMessage(null)
    const cur = latest.current
    const cutoff = cur ? cur.server_time : Date.now() / 1000
    if (cur?.running && cur.input.mode !== 'demo') {
      setDemoMessage('The guided demo needs Demo simulation mode, so the agent was restarted in that mode.')
      await post('/api/stop')
      await sleep(300)
    }
    if (!cur?.running || cur.input.mode !== 'demo') {
      const r = await post('/api/start', { mode: 'demo', cloud: settings.cloud })
      if (!r.ok) {
        setActionError(r.error ?? { kind: 'service_error', message: 'Start failed.' })
        setBusy(false)
        return
      }
      await sleep(600)
    }
    setDemoDone({})
    setDemoCutoff(cutoff - 0.05)
    const r = await post('/api/demo/run')
    if (!r.ok) {
      setActionError(r.error ?? { kind: 'service_error', message: 'Demo run failed.' })
      setDemoCutoff(null)
    }
    setBusy(false)
  }, [settings.cloud])

  return (
    <Ctx.Provider
      value={{
        state, reachable, checking, retry, settings, setSettings, busy, actionError,
        clearActionError: () => setActionError(null), start, stop, runDemo,
        demoDone, demoStarted: demoCutoff !== null, demoMessage,
      }}
    >
      {children}
    </Ctx.Provider>
  )
}
