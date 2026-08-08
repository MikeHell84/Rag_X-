import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Agent, AgentType } from './types'
import AgentCard from './components/AgentCard'
import AgentForm from './components/AgentForm'
import PlatformConfigForm from './components/PlatformConfigForm'
import ChatQuery from './components/ChatQuery'
import DocumentsList from './components/DocumentsList'
import ChatDocuments from './components/ChatDocuments'

type Tab = 'agents' | 'search' | 'chat' | 'documents' | 'docs_chat'

const TABS: { key: Tab; label: string }[] = [
  { key: 'agents', label: 'Agentes IA' },
  { key: 'search', label: 'Búsqueda' },
  { key: 'chat', label: 'Chat' },
  { key: 'documents', label: 'Documentos' },
  { key: 'docs_chat', label: 'Chat y documentos' }
]

const FILTERS: { key: AgentType | 'all'; label: string }[] = [
  { key: 'all', label: 'Todos' },
  { key: 'chat', label: 'Generación' },
  { key: 'embedding', label: 'Embeddings' },
  { key: 'reranker', label: 'Re-ranking' }
]

export default function App() {
  const [tab, setTab] = useState<Tab>('agents')
  const [agents, setAgents] = useState<Agent[]>([])
  const [filter, setFilter] = useState<AgentType | 'all'>('all')
  const [editing, setEditing] = useState<Agent | null | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setAgents(await api.agents())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const visible = filter === 'all' ? agents : agents.filter((a) => a.agent_type === filter)

  return (
    <div className="admin">
      <header className="top">
        <h1>Panel de Administración · RAG</h1>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'on' : ''} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>
        <nav className="jumps">
          <a href="http://localhost:8080" target="_blank" rel="noreferrer">Dashboard</a>
          <a href="http://localhost:8501" target="_blank" rel="noreferrer">Pipeline</a>
        </nav>
      </header>

      {tab === 'agents' ? (
        <main className="agents">
          <div className="toolbar">
            <div className="chips">
              {FILTERS.map((f) => (
                <button key={f.key} className={`chip ${filter === f.key ? 'on' : ''}`} onClick={() => setFilter(f.key)}>
                  {f.label}
                </button>
              ))}
            </div>
            <button className="primary" onClick={() => setEditing(null)}>+ Nuevo agente</button>
          </div>
          {error && <p className="err banner">No se pudo cargar: {error}</p>}
          {loading ? (
            <p className="muted">Cargando agentes…</p>
          ) : visible.length === 0 ? (
            <p className="muted">No hay agentes de este tipo. Crea el primero.</p>
          ) : (
            <div className="grid">
              {visible.map((a) => (
                <AgentCard key={a.id} agent={a} onChanged={load} onEdit={setEditing} />
              ))}
            </div>
          )}
        </main>
      ) : tab === 'search' ? (
        <main className="agents">
          <PlatformConfigForm />
        </main>
      ) : tab === 'chat' ? (
        <main className="agents">
          <ChatQuery />
        </main>
      ) : tab === 'documents' ? (
        <main className="agents">
          <DocumentsList />
        </main>
      ) : (
        <main className="agents">
          <ChatDocuments />
        </main>
      )}

      {editing !== undefined && (
        <AgentForm agent={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); load() }} />
      )}
    </div>
  )
}
