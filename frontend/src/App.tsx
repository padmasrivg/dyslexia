import { useEffect, useRef, useState } from 'react'
import { useAgent } from './agent'
import { usePrefs } from './prefs'
import { Reveal } from './ui'
import Dashboard from './views/Dashboard'
import Live from './views/Live'
import Privacy from './views/Privacy'
import { speak } from './views/shared'

const VIEWS = [
  { id: 'dashboard', label: 'Home', title: 'Welcome', C: Dashboard },
  { id: 'live', label: 'Reading Room', title: 'Interactive Reading Room', C: Live },
  { id: 'privacy', label: 'Privacy & Safety', title: 'Privacy and Safety', C: Privacy },
] as const

const fromHash = () => {
  const id = window.location.hash.replace(/^#\/?/, '')
  return VIEWS.find((v) => v.id === id)?.id ?? 'dashboard'
}

export default function App() {
  const { state, reachable, retry, checking } = useAgent()
  const { prefs, set } = usePrefs()
  const [view, setView] = useState<string>(fromHash)
  const h1 = useRef<HTMLHeadingElement>(null)
  const first = useRef(true)
  const [announce, setAnnounce] = useState('')
  const lastLabel = useRef('')
  const lastAssist = useRef<number | null>(null)

  useEffect(() => {
    const on = () => setView(fromHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  const cur = VIEWS.find((v) => v.id === view) ?? VIEWS[0]
  useEffect(() => {
    document.title = `${cur.title} | Dyslexia Vision`
    if (first.current) { first.current = false; return }
    h1.current?.focus()
  }, [cur])

  useEffect(() => {
    if (!state) return
    const label = state.status.label
    const a = state.assistance
    if (a && a.id !== lastAssist.current) {
      lastAssist.current = a.id
      setAnnounce(`Explanation for ${a.word}. ${a.definition}`)
      if (!a.has_audio) {
        speak(`${a.word}. ${a.definition}`)
      }
    } else if (label !== lastLabel.current) {
      setAnnounce(`Status: ${label}`)
    }
    lastLabel.current = label
  }, [state])

  const simulation = !!state?.input.simulation
  const isLive = state?.running

  return (
    <div className="min-h-screen flex flex-col bg-page">
      <a
        href="#main"
        className="skip"
        onClick={(e) => {
          e.preventDefault()
          document.getElementById('main')?.focus()
        }}
      >
        Skip to main content
      </a>

      {/* Top Google-style Navigation Bar */}
      <header className="sticky top-0 z-40 w-full border-b border-rule bg-surface/95 backdrop-blur-md shadow-xs transition-all">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
          {/* Brand Logo with Google 4-Color Dots */}
          <a href="#/dashboard" className="flex items-center gap-3 no-underline">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gblue-light text-gblue font-bold shadow-xs">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
              </svg>
            </div>
            <div>
              <span className="text-xl font-extrabold tracking-tight text-ink block leading-none">
                Dyslexia Vision
              </span>
              <span className="text-[11px] font-semibold text-muted tracking-wide mt-0.5 block">
                Smart Reading Companion
              </span>
            </div>
          </a>

          {/* Center Navigation Tabs with Rounded Pill Indicator */}
          <nav aria-label="Main Navigation" className="hidden md:flex items-center gap-1">
            {VIEWS.map((v) => (
              <a
                key={v.id}
                className="nav-link"
                href={`#/${v.id}`}
                aria-current={v.id === view ? 'page' : undefined}
              >
                {v.label}
              </a>
            ))}
          </nav>

          {/* Right Action & Display Preferences */}
          <div className="flex items-center gap-3">
            {/* Status Chip */}
            <div className="hidden sm:flex items-center gap-2">
              {simulation && (
                <span className="tag text-xs font-semibold tag-google-blue">
                  Sample Story
                </span>
              )}
              <span className={`tag text-xs font-bold ${isLive ? 'tag-google-green' : 'bg-page text-muted'}`}>
                <span className={`inline-block h-2 w-2 rounded-full ${isLive ? 'bg-ggreen animate-pulse' : 'bg-control'}`} />
                {isLive ? 'Helper Active' : 'Ready'}
              </span>
            </div>

            {/* Accessibility Display Controls */}
            <div className="flex items-center gap-1.5 border-l border-rule/80 pl-3">
              <button
                type="button"
                className="btn btn-sm"
                title="Make text smaller"
                aria-label="Make text smaller"
                disabled={prefs.size === 0}
                onClick={() => set({ size: (prefs.size - 1) as 0 | 1 })}
              >
                A-
              </button>
              <button
                type="button"
                className="btn btn-sm"
                title="Make text larger"
                aria-label="Make text larger"
                disabled={prefs.size === 2}
                onClick={() => set({ size: (prefs.size + 1) as 1 | 2 })}
              >
                A+
              </button>
              <button
                type="button"
                className={`btn btn-sm ${prefs.contrast ? 'btn-dark' : ''}`}
                title={`High contrast: ${prefs.contrast ? 'On' : 'Off'}`}
                aria-label="Toggle high contrast"
                aria-pressed={prefs.contrast}
                onClick={() => set({ contrast: !prefs.contrast })}
              >
                {prefs.contrast ? 'Contrast: High' : 'Contrast'}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Navigation Row */}
        <div className="flex md:hidden border-t border-rule/60 px-4 py-2 overflow-x-auto gap-1">
          {VIEWS.map((v) => (
            <a
              key={v.id}
              className="nav-link whitespace-nowrap text-xs py-1.5 px-3"
              href={`#/${v.id}`}
              aria-current={v.id === view ? 'page' : undefined}
            >
              {v.label}
            </a>
          ))}
        </div>
      </header>

      {/* Main Content Area */}
      <main id="main" tabIndex={-1} className="flex-1 mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 outline-none">
        <h1 ref={h1} tabIndex={-1} className="sr-only">
          {cur.title}
        </h1>

        <Reveal show={!reachable}>
          <div className="google-card mb-6 border-gred bg-gred-light/30 text-gred" role="alert">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-gred/10 text-gred font-bold text-lg">!</div>
              <div className="flex-1">
                <p className="font-bold text-lg text-ink">Assistant is offline</p>
                <p className="mt-1 text-sm text-muted">
                  The local assistant application is starting up or disconnected. Click retry to connect.
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm mt-3"
                  onClick={retry}
                  disabled={checking}
                >
                  {checking ? 'Connecting...' : 'Reconnect Now'}
                </button>
              </div>
            </div>
          </div>
        </Reveal>

        {!state ? (
          <div className="google-card text-center py-20">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-3 border-gblue border-t-transparent mb-3" />
            <p className="text-muted text-base font-medium">Opening your reading assistant...</p>
          </div>
        ) : (
          <cur.C />
        )}
      </main>

      {/* Friendly Footer */}
      <footer className="border-t border-rule bg-surface py-6 text-center text-xs text-muted">
        <div className="mx-auto max-w-7xl px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p>Dyslexia Vision. Empowering readers with gentle, real-time reading assistance.</p>
          <div className="flex items-center gap-5">
            <a href="#/live" className="hover:text-gblue font-medium no-underline">Reading Room</a>
            <a href="#/privacy" className="hover:text-gblue font-medium no-underline">Privacy & Safety</a>
          </div>
        </div>
      </footer>

      {/* Polite Screen Reader Live Region */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announce}
      </div>
    </div>
  )
}
