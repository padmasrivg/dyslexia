import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { explainKind } from './format'
import type { ApiError } from './types'

const T = { duration: 0.15, ease: 'easeOut' as const }

/** Small enter/exit transition for content whose text changes with the state. */
export function Swap({ id, children, className }: { id: string | number; children: ReactNode; className?: string }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={id}
        className={className}
        initial={{ opacity: 0, y: 3 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -3 }}
        transition={T}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

/** Block that fades in and out as it is added or removed. */
export function Reveal({ show, children, className }: { show: boolean; children: ReactNode; className?: string }) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          className={className}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          style={{ overflow: 'hidden' }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function StateText({ state, label }: { state: string; label: string }) {
  const isErr = state === 'ERROR'
  const isProc = state === 'REQUESTING_ASSISTANCE' || state === 'STUCK_WORD' || state === 'FOCUSING'
  const isOk = state === 'ASSISTING' || state === 'READING'
  
  const statusColor = isErr ? 'var(--c-err)' : isProc ? 'var(--c-proc)' : isOk ? 'var(--c-ok)' : 'var(--c-muted)'
  const statusBg = isErr ? 'rgba(158, 43, 37, 0.08)' : isProc ? 'rgba(138, 82, 0, 0.08)' : isOk ? 'rgba(31, 107, 60, 0.08)' : 'var(--c-surface)'

  return (
    <Swap id={label}>
      <div className="flex flex-wrap items-center gap-3">
        <div
          className="inline-flex items-center gap-2 px-3 py-1 rounded-md border font-bold"
          style={{ borderColor: statusColor, background: statusBg, color: statusColor }}
        >
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: statusColor }} aria-hidden="true" />
          <span className="text-2xl">{label}</span>
        </div>
        <span className="muted text-sm">State code: <code>{state}</code></span>
      </div>
    </Swap>
  )
}

export function ErrorBlock({ error, title }: { error: ApiError; title?: string }) {
  return (
    <div className="panel border-err" role="alert" style={{ borderColor: 'var(--c-err)', background: 'rgba(158, 43, 37, 0.05)' }}>
      <p className="err-text font-bold text-lg">{title ?? 'Problem'}: {error.kind}</p>
      <p className="mt-1">{explainKind(error.kind)}</p>
      {error.message && <p className="muted mt-2 text-sm">Message from agent: {error.message}</p>}
    </div>
  )
}

export function Progress({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      className="bar"
    >
      <div style={{ width: `${pct}%` }} />
    </div>
  )
}

export function SimTag({ simulation }: { simulation: boolean }) {
  return (
    <span className="tag tag-status">
      {simulation ? 'SIMULATION MODE' : 'LIVE INPUT'}
    </span>
  )
}
