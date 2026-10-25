/*
 * Layered organic wave contours with refined opacity layers.
 * Retains high readability and contrast for foreground text.
 */
export function WaveBand() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 1440 220"
      preserveAspectRatio="none"
      className="absolute inset-0 h-full w-full pointer-events-none opacity-80"
    >
      <path
        style={{ fill: 'var(--w1)' }}
        d="M0,80 C320,130 520,40 820,95 C1120,150 1280,70 1440,105 L1440,220 L0,220 Z"
      />
      <path
        style={{ fill: 'var(--w2)' }}
        d="M0,125 C360,170 600,100 900,140 C1200,180 1340,120 1440,150 L1440,220 L0,220 Z"
      />
      <path
        style={{ fill: 'var(--w3)' }}
        d="M0,170 C400,205 680,165 960,185 C1240,205 1360,175 1440,190 L1440,220 L0,220 Z"
      />
    </svg>
  )
}
