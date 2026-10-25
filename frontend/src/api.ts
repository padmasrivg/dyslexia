import type { ActionResult, DeviceList } from './types'

export async function post<T = ActionResult>(path: string, body?: unknown): Promise<T> {
  try {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    })
    const j = (await r.json().catch(() => null)) as T | null
    if (j) return j
    return (r.ok ? { ok: true } : { ok: false, error: { kind: 'service_error', message: `HTTP ${r.status}` } }) as T
  } catch {
    return { ok: false, error: { kind: 'network', message: 'The local agent did not answer.' } } as T
  }
}

export async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(path)
    if (!r.ok) return null
    return (await r.json()) as T
  } catch {
    return null
  }
}

export async function getDevices(probe: boolean): Promise<DeviceList | null> {
  try {
    const r = await fetch(`/api/devices${probe ? '?probe_cameras=true' : ''}`)
    if (!r.ok) return null
    return (await r.json()) as DeviceList
  } catch {
    return null
  }
}
