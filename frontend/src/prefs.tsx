import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { MotionConfig } from 'motion/react'

export interface Prefs { size: 0 | 1 | 2; contrast: boolean; reduce: boolean }
const KEY = 'dva-prefs'
const DEFAULT: Prefs = { size: 0, contrast: false, reduce: false }

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const p = JSON.parse(raw) as Partial<Prefs>
      const size = p.size === 1 || p.size === 2 ? p.size : 0
      return { size, contrast: !!p.contrast, reduce: !!p.reduce }
    }
  } catch { /* storage unavailable, use defaults */ }
  return DEFAULT
}

const Ctx = createContext<{ prefs: Prefs; set: (p: Partial<Prefs>) => void }>({ prefs: DEFAULT, set: () => {} })
export const usePrefs = () => useContext(Ctx)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(load)
  useEffect(() => {
    const d = document.documentElement
    d.dataset.size = String(prefs.size)
    d.dataset.contrast = prefs.contrast ? 'high' : 'normal'
    d.dataset.reduce = prefs.reduce ? 'yes' : 'no'
    try { localStorage.setItem(KEY, JSON.stringify(prefs)) } catch { /* ignore */ }
  }, [prefs])
  const set = (p: Partial<Prefs>) => setPrefs((c) => ({ ...c, ...p }))
  return (
    <Ctx.Provider value={{ prefs, set }}>
      <MotionConfig reducedMotion={prefs.reduce ? 'always' : 'user'}>{children}</MotionConfig>
    </Ctx.Provider>
  )
}
