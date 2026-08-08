import type { Agent, DocumentDoc, PlatformConfig, Conversation, ConversationMessage } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers:
      options && !(options.body instanceof FormData)
        ? { 'Content-Type': 'application/json', ...(options.headers ?? {}) }
        : options?.headers,
    ...options
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = typeof body === 'string'
        ? body
        : body?.error || body?.detail || JSON.stringify(body)
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
    request<PlatformConfig>('/platform-config/', { method: 'PUT', body: JSON.stringify(c) }),
  documents: () => request<{ count: number; results: DocumentDoc[] }>('/documents/'),
  uploadDocument: (file: File, topic?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (topic) form.append('topic', topic)
    return request<{ id: number; task_id: string; status: string }>(
      '/documents/upload/',
      { method: 'POST', body: form }
    )
  },
  documentFromUrl: (url: string, topic?: string) =>
    request<{ id: number; task_id: string; status: string }>(
      '/documents/from-url/',
      { method: 'POST', body: JSON.stringify({ url, topic }) }
    ),
  deleteDocument: (id: number) => request<void>(`/documents/${id}/`, { method: 'DELETE' }),
  updateDocument: (id: number, data: { title?: string; topic?: string; url?: string }) =>
    request<DocumentDoc>(`/documents/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  retryDocument: (id: number) => request<{ id: number; task_id: string; status: string }>(
    `/documents/${id}/retry/`, { method: 'POST' }
  ),
  reindexAll: () => request<{ queued: number; task_ids: number[] }>(
    '/documents/reindex/', { method: 'POST' }
  ),
  conversations: (params?: { topic?: string; agent_id?: number; session?: string }) => {
    const qs = new URLSearchParams()
    if (params?.topic) qs.set('topic', params.topic)
    if (params?.agent_id) qs.set('agent_id', String(params.agent_id))
    if (params?.session) qs.set('session', params.session)
    return request<{ count: number; results: Conversation[] }>(`/conversations/?${qs.toString()}`)
  },
  createConversation: (data: Partial<Conversation>) =>
    request<Conversation>('/conversations/', { method: 'POST', body: JSON.stringify(data) }),
  getConversation: (id: number) => request<Conversation>(`/conversations/${id}/`),
  updateConversation: (id: number, data: Partial<Conversation>) =>
    request<Conversation>(`/conversations/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteConversation: (id: number) => request<void>(`/conversations/${id}/`, { method: 'DELETE' }),
  addMessage: (conversationId: number, role: string, content: string) =>
    request<ConversationMessage>(`/conversations/${conversationId}/messages/`, {
      method: 'POST',
      body: JSON.stringify({ role, content })
    }),
  createQuery: (q: { question: string; top_k?: number }) =>
    request<{ task_id: string; status: string; queued: boolean }>('/query/', {
      method: 'POST',
      body: JSON.stringify(q)
    }),
  queryResult: (taskId: string) => request<{ status: string; result?: any; error?: string }>(`/query/${taskId}/`)
}
