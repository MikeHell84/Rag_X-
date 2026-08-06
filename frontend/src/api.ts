import type { Agent, PlatformConfig } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = typeof body === 'string' ? body : JSON.stringify(body)
    } catch {
      /* sin cuerpo JSON */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  agents: () => request<Agent[]>('/agents/'),
  createAgent: (a: Partial<Agent>) => request<Agent>('/agents/', { method: 'POST', body: JSON.stringify(a) }),
  updateAgent: (id: number, a: Partial<Agent>) =>
    request<Agent>(`/agents/${id}/`, { method: 'PATCH', body: JSON.stringify(a) }),
  deleteAgent: (id: number) => request<void>(`/agents/${id}/`, { method: 'DELETE' }),
  activate: (id: number) => request<Agent>(`/agents/${id}/activate/`, { method: 'POST' }),
  deactivate: (id: number) => request<Agent>(`/agents/${id}/deactivate/`, { method: 'POST' }),
  testAgent: (id: number, probe?: string) =>
    request<{ ok: boolean; response?: string; dim?: number; error?: string }>(`/agents/${id}/test/`, {
      method: 'POST',
      body: JSON.stringify({ probe })
    }),
  platformConfig: () => request<PlatformConfig>('/platform-config/'),
  savePlatformConfig: (c: PlatformConfig) =>
    request<PlatformConfig>('/platform-config/', { method: 'PUT', body: JSON.stringify(c) })
}
