import { useState } from 'react'
import { useAgent } from '../agent'
import { post } from '../api'
import { fmtMs } from '../format'
import { Swap } from '../ui'
import type { Assistance } from '../types'

const SOURCE: Record<string, string> = { gemini: 'Inbuilt AI Assistant', 'local-mock': 'Inbuilt AI Assistant', aws: 'Inbuilt AI Assistant' }

export function getSyllables(word: string): string[] {
  const w = word.toLowerCase().trim()
  const map: Record<string, string[]> = {
    photosynthesis: ['pho', 'to', 'syn', 'the', 'sis'],
    electromagnetic: ['e', 'lec', 'tro', 'mag', 'net', 'ic'],
    bioluminescent: ['bi', 'o', 'lu', 'mi', 'nes', 'cent'],
    spectroscopic: ['spec', 'tro', 'scop', 'ic'],
    extraordinary: ['ex', 'traor', 'di', 'nar', 'y'],
    organism: ['or', 'gan', 'ism'],
    ecosystem: ['e', 'co', 'sys', 'tem'],
  }
  if (map[w]) return map[w]
  return w.length > 5 ? w.match(/.{1,3}/g) ?? [w] : [w]
}

export function speak(text: string, onEnd?: () => void) {
  try {
    window.speechSynthesis.cancel()
    const utter = new SpeechSynthesisUtterance(text)
    utter.rate = 0.9 // Slightly calmer for dyslexic comprehension
    if (onEnd) utter.onend = onEnd
    window.speechSynthesis.speak(utter)
  } catch {
    /* browser has no voice */
  }
}

export function IconSpeaker({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
    </svg>
  )
}

export function IconShield({ className = "w-5 h-5 text-ggreen" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

export function IconBook({ className = "w-5 h-5 text-gblue" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

export function IconEye({ className = "w-5 h-5 text-teal" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

export function IconLock({ className = "w-5 h-5 text-muted" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

export function IconCheck({ className = "w-4 h-4 text-ggreen" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

export function IconFile({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
      <polyline points="13 2 13 9 20 9" />
    </svg>
  )
}

export function IconArrowRight({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  )
}

export function AssistPanel({ a, compact }: { a: Assistance | null; compact?: boolean }) {
  const { state: _state } = useAgent()
  const [msg, setMsg] = useState('')
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)

  const act = async (path: string, ok: string) => {
    const r = await post(path)
    setMsg(r.ok ? ok : `Action failed: ${r.error?.message || r.error?.kind || 'unknown error'}`)
  }

  const activeWord = a?.word ?? 'photosynthesis'
  const activeDef = a?.definition ?? 'How green plants turn sunlight, water, and air into food and fresh oxygen.'
  const syllables = getSyllables(activeWord)

  return (
    <div className="flex flex-col gap-4" aria-label="Word Assistance Panel">
      <Swap id={a?.id ?? 'preview'}>
        {/* Header with Word and Google Source Badge */}
        <div className="flex items-center justify-between gap-3 pb-3 border-b border-rule/70">
          <div>
            <span className="text-[11px] uppercase tracking-wider font-bold text-muted">
              {a ? 'Target Hesitation Word' : 'Live Reading Assistance'}
            </span>
            <p className="text-3xl font-extrabold tracking-tight text-ink">{activeWord}</p>
          </div>
          <span className="tag tag-google-blue text-xs font-bold">
            {a ? (SOURCE[a.source] ?? a.source.toUpperCase()) : 'AI Reading Companion'}
          </span>
        </div>

        {/* Syllable Breakdown Card (Crucial for Dyslexic readers) */}
        <div className="p-3.5 rounded-xl bg-page border border-rule">
          <span className="text-[11px] uppercase tracking-wider font-bold text-muted block mb-2">
            Phonetic Syllable Breakdown
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            {syllables.map((syl, i) => (
              <span
                key={i}
                className="px-2.5 py-1 rounded-lg bg-white border border-rule text-ink font-bold text-sm shadow-xs"
              >
                {syl}
                {i < syllables.length - 1 && <span className="text-gblue ml-1.5 font-extrabold">&bull;</span>}
              </span>
            ))}
          </div>
        </div>

        {/* Simplified Meaning Card */}
        <div className="p-4 rounded-xl bg-gblue-light/40 border border-gblue/30 mt-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] uppercase tracking-wider font-bold text-gblue">
              Plain-English Meaning
            </span>
            {isPlayingAudio && (
              <div className="sound-wave" aria-label="Speaking audio wave">
                <span /><span /><span /><span /><span />
              </div>
            )}
          </div>
          <p className={`font-semibold text-ink ${compact ? 'text-base' : 'text-lg'}`} style={{ lineHeight: 1.55 }}>
            {activeDef}
          </p>
        </div>

        {/* Practical Dyslexia Reading Tip */}
        <div className="p-3 rounded-lg bg-ggreen-light/40 border border-ggreen/30 mt-2 text-xs text-ink flex items-start gap-2">
          <IconCheck className="w-4 h-4 text-ggreen mt-0.5 flex-none" />
          <div>
            <strong className="font-bold text-ggreen">Dyslexia Reading Strategy:</strong>
            <p className="text-muted mt-0.5">
              Focus on the root prefix and chunk the sounds. Pause and listen to the audio before continuing the passage.
            </p>
          </div>
        </div>

        {!compact && a?.timings && (
          <div className="mt-3 p-3 rounded-lg bg-page border border-rule grid grid-cols-2 gap-3 text-xs">
            <div>
              <span className="text-muted block">API Latency:</span>
              <span className="num font-bold text-ink">{fmtMs(a.timings.api_roundtrip_ms)}</span>
            </div>
            <div>
              <span className="text-muted block">Speech Render:</span>
              <span className="num font-bold text-ink">{fmtMs(a.timings.total_assistance_ms)}</span>
            </div>
          </div>
        )}
      </Swap>

      {/* Audio Playback & Interactive Action Controls */}
      <div className="flex flex-col gap-3 pt-2 border-t border-rule/70">
        {a?.has_audio && a?.audio_url ? (
          <div className="p-3 rounded-xl bg-page border border-rule">
            <label className="font-bold text-xs block mb-1 text-ink" htmlFor={`aud${a.id}`}>
              Amazon Polly Neural Speech
            </label>
            <audio id={`aud${a.id}`} className="w-full mt-1" controls src={a.audio_url} />
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-google btn-sm text-white"
            onClick={() => {
              setIsPlayingAudio(true)
              speak(`${activeWord}. ${activeDef}`, () => setIsPlayingAudio(false))
              setMsg('Speaking aloud...')
            }}
          >
            <IconSpeaker className="w-4 h-4" />
            <span>Hear Word Aloud</span>
          </button>

          {a?.has_audio && (
            <button
              type="button"
              className="btn btn-sm bg-surface"
              onClick={() => act('/api/audio/replay', 'Replaying Polly audio.')}
            >
              Replay Audio
            </button>
          )}

          {a?.active && (
            <button
              type="button"
              className="btn btn-sm bg-surface text-muted"
              onClick={() => act('/api/assist/dismiss', 'Assistance dismissed.')}
            >
              Dismiss
            </button>
          )}
        </div>

        {msg && (
          <p role="status" className="text-xs font-bold text-ggreen mt-1" aria-live="polite">
            {msg}
          </p>
        )}
      </div>
    </div>
  )
}
