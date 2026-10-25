import { useState } from 'react'
import { useAgent } from '../agent'
import { getSyllables, speak, IconSpeaker, IconBook, IconEye, IconCheck, IconFile } from './shared'

export default function Diagnostics() {
  const { state: s } = useAgent()
  const [speakingWord, setSpeakingWord] = useState<string | null>(null)

  if (!s) return null

  const handleSpeak = (word: string, def: string) => {
    setSpeakingWord(word)
    speak(`${word}. ${def}`, () => setSpeakingWord(null))
  }

  const lr = s.last_request
  const a = s.assistance
  const c = s.metrics.counters

  // Actual word assisted during this reading session (NO default photosynthesis!)
  const liveWord = a?.word || lr?.word
  const liveDef = a?.definition
  const liveContext = a?.context || lr?.context
  const syllables = liveWord ? getSyllables(liveWord) : []

  const wordsOnPage = s.words?.length || 0
  const wordsHelped = c.assist_requests || (a ? 1 : 0)

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-extrabold text-ink tracking-tight">Reading Insights</h2>
        <p className="text-muted text-sm mt-0.5">
          Your reading milestones, vocabulary progress, and personalized comprehension metrics.
        </p>
      </div>

      {/* Key Reading Progress Cards */}
      <section aria-labelledby="h-kpi" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <h3 id="h-kpi" className="sr-only">Key Reading Metrics</h3>

        {/* Words On Page */}
        <div className="card-panel flex flex-col justify-between border-t-4 border-t-gblue">
          <div>
            <span className="text-xs font-bold text-muted uppercase tracking-wider block">Words On Page</span>
            <p className="num text-3xl font-extrabold text-ink mt-1">
              {wordsOnPage > 0 ? wordsOnPage : '—'}
            </p>
          </div>
          <p className="text-xs text-muted mt-3">Words rendered with dyslexia-friendly spacing</p>
        </div>

        {/* Words Overcome */}
        <div className="card-panel flex flex-col justify-between border-t-4 border-t-ggreen">
          <div>
            <span className="text-xs font-bold text-muted uppercase tracking-wider block">Words Mastered</span>
            <p className="num text-3xl font-extrabold text-ggreen mt-1">
              {wordsHelped}
            </p>
          </div>
          <p className="text-xs text-muted mt-3">Challenging words broken down with speech & syllables</p>
        </div>

        {/* Reading Pacing & Flow */}
        <div className="card-panel flex flex-col justify-between border-t-4 border-t-gyellow">
          <div>
            <span className="text-xs font-bold text-muted uppercase tracking-wider block">Reading Pacing</span>
            <p className="text-2xl font-bold text-ink mt-1">Calm & Steady</p>
          </div>
          <p className="text-xs text-muted mt-3">
            {s.config.dwell_threshold_s}s comfortable pause threshold for assistance
          </p>
        </div>

        {/* Reading Companion */}
        <div className="card-panel flex flex-col justify-between border-t-4 border-t-teal">
          <div>
            <span className="text-xs font-bold text-muted uppercase tracking-wider block">Reading Helper</span>
            <p className="text-2xl font-bold text-teal mt-1">Active & Ready</p>
          </div>
          <p className="text-xs text-muted mt-3">Child-friendly plain English explanations</p>
        </div>
      </section>

      {/* Real Vocabulary Assistance Log (Shown only when real words are queried) */}
      <section aria-labelledby="h-vocab" className="card-panel">
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-rule">
          <div>
            <h3 id="h-vocab" className="text-xl font-bold text-ink">Words Looked Up This Session</h3>
            <p className="text-xs text-muted mt-0.5">
              Review words you hesitated on with phonetic syllable breakdowns and clear explanations.
            </p>
          </div>
          {liveWord && (
            <span className="tag tag-google-green text-xs font-bold">
              Assisted
            </span>
          )}
        </div>

        {liveWord ? (
          <div className="p-5 rounded-2xl bg-page border border-rule/80 flex flex-col md:flex-row items-start md:items-center justify-between gap-5">
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <span className="text-3xl font-extrabold text-ink tracking-tight">{liveWord}</span>
                {liveDef && (
                  <button
                    type="button"
                    className={`btn btn-sm text-xs py-1 px-3 flex items-center gap-1.5 ${speakingWord === liveWord ? 'btn-google text-white' : 'bg-white text-gblue border-gblue/40'}`}
                    onClick={() => handleSpeak(liveWord, liveDef)}
                    title="Pronounce word and definition clearly"
                  >
                    <IconSpeaker className="w-3.5 h-3.5" />
                    <span>{speakingWord === liveWord ? 'Speaking...' : 'Listen Aloud'}</span>
                  </button>
                )}
              </div>

              {/* Syllable Breakdown */}
              {syllables.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mt-3">
                  <span className="text-xs font-bold text-muted mr-1">Syllables:</span>
                  {syllables.map((syl, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-md bg-white border border-rule text-sm font-bold text-gblue shadow-2xs"
                    >
                      {syl}
                    </span>
                  ))}
                </div>
              )}

              {/* Definition */}
              {liveDef && (
                <p className="text-sm font-medium text-ink mt-3 leading-relaxed">
                  &ldquo;{liveDef}&rdquo;
                </p>
              )}

              {/* Sentence Context */}
              {liveContext && (
                <p className="text-xs text-muted italic mt-2">
                  Sentence Context: &ldquo;{liveContext}&rdquo;
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="p-6 rounded-2xl bg-page border border-rule/70 text-center">
            <IconBook className="w-8 h-8 text-gblue mx-auto mb-2" />
            <p className="font-bold text-ink text-base">No words looked up yet</p>
            <p className="text-xs text-muted mt-1 max-w-md mx-auto">
              As you read in the Reading Room, pause your pointer or eyes on any word you find tricky. 
              Its syllable breakdown and child-friendly definition will automatically appear here!
            </p>
          </div>
        )}
      </section>

      {/* Dyslexia Support Tools Active */}
      <section aria-labelledby="h-strategies" className="card-panel">
        <h3 id="h-strategies" className="text-xl font-bold text-ink mb-2">How This Reading Assistant Helps You</h3>
        <p className="text-muted text-sm mb-5">
          Proven reading aids active in your reading sessions to reduce cognitive load and build fluency.
        </p>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="p-4 rounded-xl bg-page border border-rule">
            <IconCheck className="w-5 h-5 text-gblue mb-2" />
            <h4 className="font-bold text-ink text-sm">Syllable Chunking</h4>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              Breaks long, complex words into smaller, manageable sounds to remove reading anxiety.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-page border border-rule">
            <IconSpeaker className="w-5 h-5 text-teal mb-2" />
            <h4 className="font-bold text-ink text-sm">Multi-Sensory Speech</h4>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              Speaks words aloud with natural speech, reinforcing visual letter shapes with clear audio.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-page border border-rule">
            <IconEye className="w-5 h-5 text-ggreen mb-2" />
            <h4 className="font-bold text-ink text-sm">Hands-Free Focus</h4>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              Pausing gently on a word for 1.5 seconds automatically brings up help without exhausting your hands.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-page border border-rule">
            <IconFile className="w-5 h-5 text-gyellow mb-2" />
            <h4 className="font-bold text-ink text-sm">High-Contrast Text</h4>
            <p className="text-xs text-muted mt-1 leading-relaxed">
              Generous letter spacing and distinct character baselines prevent letter flipping and crowding.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
