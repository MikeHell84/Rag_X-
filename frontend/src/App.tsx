import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Agent, AgentType } from './types'
import AgentCard from './components/AgentCard'
import AgentForm from './components/AgentForm'
import PlatformConfigForm from './components/PlatformConfigForm'

type Tab = 'agents' | 'config'

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
          <button className={tab === 'agents' ? 'on' : ''} onClick={() => setTab('agents')}>Agentes IA</button>
          <button className={tab === 'config' ? 'on' : ''} onClick={() => setTab('config')}>Búsqueda</button>
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
      ) : (
        <main className="agents">
          <PlatformConfigForm />
        </main>
      )}

      {editing !== undefined && (
        <AgentForm agent={editing} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); load() }} />
      )}
    </div>
  )
}
