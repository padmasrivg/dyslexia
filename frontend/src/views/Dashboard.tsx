import { useState } from 'react'
import { useAgent } from '../agent'
import { ErrorBlock, Progress, Reveal } from '../ui'
import { speak, IconSpeaker, IconBook, IconEye, IconFile, IconCheck, IconArrowRight } from './shared'

export default function Dashboard() {
  const { state: s, settings, setSettings, actionError } = useAgent()
  const [isSpeaking, setIsSpeaking] = useState(false)

  if (!s) return null

  return (
    <div className="flex flex-col gap-10 animate-fade-in">
      {/* Hero Showcase Section */}
      <section className="relative grid gap-10 lg:grid-cols-12 lg:items-center py-4 lg:py-6">
        {/* Left Column: Value Proposition & Actions */}
        <div className="flex flex-col items-start gap-5 lg:col-span-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-gblue/30 bg-gblue-light px-3.5 py-1 text-xs font-bold text-gblue shadow-xs">
            <span className="flex h-2 w-2 rounded-full bg-gblue" />
            Designed for Dyslexic Readers
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight text-ink sm:text-5xl lg:text-6xl leading-[1.08]">
            Dyslexia Vision
          </h1>

          <p className="text-xl font-medium text-ink sm:text-2xl leading-snug">
            Read with confidence, one word at a time.
          </p>

          <p className="text-muted text-base sm:text-lg leading-relaxed max-w-xl">
            Dyslexia Vision follows your reading flow in real time. When you pause or hesitate on a challenging word, it quietly provides syllable breakdowns, clear plain-language definitions, and spoken pronunciation.
          </p>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <a
              href="#/live"
              className="btn btn-primary px-7 py-3 text-base font-bold shadow-sm flex items-center gap-2"
            >
              <span>Launch Reading Room</span>
              <IconArrowRight className="w-4 h-4" />
            </a>

            <button
              type="button"
              className="btn px-6 py-3 text-sm font-semibold bg-surface border border-rule hover:bg-page"
              onClick={() => {
                setSettings({ mode: 'demo' })
                window.location.hash = '#/live'
              }}
              title="Practice with an interactive sample passage in the Reading Room"
            >
              <span>Try Sample Passage</span>
            </button>
          </div>

          <Reveal show={!!actionError}>
            {actionError && (
              <div className="w-full mt-2">
                <ErrorBlock error={actionError} title="Notice" />
              </div>
            )}
          </Reveal>
        </div>

        {/* Right Column: Interactive Reading Showcase Card */}
        <div className="lg:col-span-6 flex justify-center lg:justify-end">
          <div className="showcase-deck w-full max-w-lg">
            {/* Background Layered Card */}
            <div className="showcase-card-back p-5 flex flex-col justify-between opacity-50 bg-[#E8EAED]">
              <div className="flex items-center justify-between text-xs font-bold text-muted">
                <span>Private on your device</span>
                <span>Calm audio support</span>
              </div>
              <div className="h-20 bg-rule/20 rounded-lg" />
            </div>

            {/* Foreground Interactive Preview Card */}
            <div className="showcase-card border border-rule shadow-md bg-surface">
              {/* Card Window Header */}
              <div className="flex items-center justify-between border-b border-rule bg-page px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full bg-gred/70" />
                  <div className="h-3 w-3 rounded-full bg-gyellow/70" />
                  <div className="h-3 w-3 rounded-full bg-ggreen/70" />
                  <span className="ml-2 text-xs font-bold tracking-wide text-muted">
                    Reading Companion Preview
                  </span>
                </div>
                <span className="tag text-[11px] font-bold tag-google-blue">
                  READY TO READ
                </span>
              </div>

              {/* Card Window Content */}
              <div className="p-5 flex flex-col gap-4">
                <div className="rounded-xl border border-rule bg-page p-4">
                  <div className="flex items-center justify-between text-xs text-muted font-bold mb-2">
                    <span>ASSISTIVE READING PREVIEW</span>
                    <span className="text-ggreen font-bold">SMART PAUSE SENSING</span>
                  </div>
                  <p className="text-base text-ink font-medium leading-relaxed">
                    Dyslexia Vision adapts to your natural reading pace. When you pause on a difficult word, it quietly provides{' '}
                    <span className="bg-gyellow-light text-[#B06000] px-2 py-0.5 rounded font-bold border border-gyellow/40">
                      syllable
                    </span>{' '}
                    breakdowns and clear pronunciation.
                  </p>
                </div>

                {/* Instant Dyslexic Breakdown Card */}
                <div className="rounded-xl border border-rule bg-white p-4 shadow-xs">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-extrabold uppercase tracking-wider text-muted">
                        Word Assistance
                      </span>
                      <h4 className="text-2xl font-bold text-ink tracking-tight">
                        syllable
                      </h4>
                    </div>
                    <span className="tag text-xs font-bold tag-google-blue">
                      Plain English
                    </span>
                  </div>

                  <p className="mt-2 text-sm font-medium text-ink leading-normal">
                    One unbroken sound unit that forms whole or part of a word.
                  </p>

                  <div className="mt-3 flex items-center justify-between border-t border-rule/60 pt-3 text-xs">
                    <div className="flex items-center gap-1.5 text-muted">
                      <span className="font-bold text-ink">Syllables:</span>
                      <span className="text-gblue font-bold">
                        syl • la • ble
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-google btn-sm text-white text-xs px-3 py-1 min-h-[30px] flex items-center gap-1.5"
                      onClick={() => {
                        setIsSpeaking(true)
                        speak('syllable. One unbroken sound unit that forms a word.', () => setIsSpeaking(false))
                      }}
                      title="Listen with text-to-speech"
                    >
                      <IconSpeaker className="w-3.5 h-3.5" />
                      <span>{isSpeaking ? 'Speaking...' : 'Hear Aloud'}</span>
                    </button>
                  </div>
                </div>

                {/* Reading Pacing Meter */}
                <div>
                  <div className="flex items-center justify-between text-xs font-bold">
                    <span className="text-muted">Pause Meter Threshold</span>
                    <span className="num text-ink">
                      1.5s (Comfortable)
                    </span>
                  </div>
                  <Progress value={1} label="Reading pause" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works - 3 Step Guide */}
      <section className="google-card">
        <h2 className="text-2xl font-extrabold text-ink mb-1">How Dyslexia Vision Works</h2>
        <p className="text-muted text-sm mb-6">Designed to be simple, supportive, and distraction-free.</p>

        <div className="grid gap-6 md:grid-cols-3">
          <div className="p-4 rounded-xl bg-page border border-rule flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-gblue block mb-2">Step 1</span>
              <h3 className="font-bold text-ink text-lg mb-2">Open Your Material</h3>
              <p className="text-sm text-muted leading-relaxed">
                Upload any PDF article, school worksheet, image of a book page, or paste text directly into the Reading Room.
              </p>
            </div>
            <span className="text-xs font-semibold text-gblue mt-4 flex items-center gap-1">
              Supports PDF, images & text
            </span>
          </div>

          <div className="p-4 rounded-xl bg-page border border-rule flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-ggreen block mb-2">Step 2</span>
              <h3 className="font-bold text-ink text-lg mb-2">Read at Your Own Pace</h3>
              <p className="text-sm text-muted leading-relaxed">
                Follow along with your eyes or pointer. The assistant operates silently in the background without rushing you.
              </p>
            </div>
            <span className="text-xs font-semibold text-ggreen mt-4 flex items-center gap-1">
              Hands-free gaze tracking
            </span>
          </div>

          <div className="p-4 rounded-xl bg-page border border-rule flex flex-col justify-between">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-teal block mb-2">Step 3</span>
              <h3 className="font-bold text-ink text-lg mb-2">Get Instant Clarity</h3>
              <p className="text-sm text-muted leading-relaxed">
                Whenever you pause on a word, instant syllable breaks and clear natural-voice pronunciation appear immediately.
              </p>
            </div>
            <span className="text-xs font-semibold text-teal mt-4 flex items-center gap-1">
              Plain English & syllables
            </span>
          </div>
        </div>
      </section>

      {/* Reading Modes Selector */}
      <section className="google-card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-2xl font-extrabold text-ink">Choose Your Reading Mode</h2>
            <p className="text-muted text-sm mt-0.5">Select how you prefer to read today.</p>
          </div>
          <a
            href="#/live"
            className="btn btn-primary btn-sm text-xs font-bold px-4 py-2 flex items-center gap-1.5"
          >
            <span>Open Reading Room</span>
            <IconArrowRight className="w-3.5 h-3.5" />
          </a>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {/* Mode 1: Interactive Reading Room */}
          <div
            className={`p-5 rounded-2xl border transition-all cursor-pointer ${settings.mode === 'demo' ? 'border-gblue bg-gblue-light/20 shadow-xs' : 'border-rule bg-page hover:border-rule/80'}`}
            onClick={() => {
              setSettings({ mode: 'demo' })
              window.location.hash = '#/live'
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <IconBook className="w-6 h-6 text-gblue" />
              <span className={`tag text-xs font-bold ${settings.mode === 'demo' ? 'tag-google-blue' : 'bg-white'}`}>
                {settings.mode === 'demo' ? 'Selected' : 'Open'}
              </span>
            </div>
            <h3 className="font-bold text-ink text-lg mb-1">Interactive Reading Room</h3>
            <p className="text-xs text-muted leading-relaxed">
              Read uploaded PDFs, documents, and passages with high-contrast text and instant word lookup.
            </p>
          </div>

          {/* Mode 2: Camera & Printed Books */}
          <div
            className={`p-5 rounded-2xl border transition-all cursor-pointer ${settings.mode === 'camera' ? 'border-gblue bg-gblue-light/20 shadow-xs' : 'border-rule bg-page hover:border-rule/80'}`}
            onClick={() => {
              setSettings({ mode: 'camera' })
              window.location.hash = '#/live'
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <IconEye className="w-6 h-6 text-ggreen" />
              <span className={`tag text-xs font-bold ${settings.mode === 'camera' ? 'tag-google-blue' : 'bg-white'}`}>
                {settings.mode === 'camera' ? 'Selected' : 'Open'}
              </span>
            </div>
            <h3 className="font-bold text-ink text-lg mb-1">Printed Books & Webcam</h3>
            <p className="text-xs text-muted leading-relaxed">
              Point your webcam at a physical book or paper worksheet on your desk for hands-free reading support.
            </p>
          </div>

          {/* Mode 3: Desktop Screen Reader */}
          <div
            className={`p-5 rounded-2xl border transition-all cursor-pointer ${settings.mode === 'screen' ? 'border-gblue bg-gblue-light/20 shadow-xs' : 'border-rule bg-page hover:border-rule/80'}`}
            onClick={() => {
              setSettings({ mode: 'screen' })
              window.location.hash = '#/live'
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <IconFile className="w-6 h-6 text-teal" />
              <span className={`tag text-xs font-bold ${settings.mode === 'screen' ? 'tag-google-blue' : 'bg-white'}`}>
                {settings.mode === 'screen' ? 'Selected' : 'Open'}
              </span>
            </div>
            <h3 className="font-bold text-ink text-lg mb-1">Computer Screen</h3>
            <p className="text-xs text-muted leading-relaxed">
              Follow along on web articles and digital reading materials directly on your computer screen.
            </p>
          </div>
        </div>
      </section>

      {/* System Readiness & Privacy Summary */}
      <section className="p-4 rounded-2xl bg-page border border-rule flex flex-wrap items-center justify-between gap-4 text-xs font-semibold text-muted">
        <div className="flex items-center gap-2">
          <IconCheck className="w-4 h-4 text-ggreen" />
          <span>Status: <strong className="text-ink">Assistant Ready</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <IconCheck className="w-4 h-4 text-ggreen" />
          <span>Word Engine: <strong className="text-ink">Inbuilt AI Active</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <IconCheck className="w-4 h-4 text-ggreen" />
          <span>Privacy: <strong className="text-ink">100% On-Device & Safe</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <IconCheck className="w-4 h-4 text-ggreen" />
          <span>Pacing: <strong className="text-ink">{s.config.dwell_threshold_s}s Pause Threshold</strong></span>
        </div>
      </section>
    </div>
  )
}
