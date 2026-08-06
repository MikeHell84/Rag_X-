import { useState } from 'react'
import { api } from '../api'
import type { Agent } from '../types'
import { PROVIDER_LABEL } from '../types'

interface Props {
  agent: Agent
  onChanged: () => void
  onEdit: (agent: Agent) => void
}

export default function AgentCard({ agent, onChanged, onEdit }: Props) {
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  async function toggleActive() {
    try {
      if (agent.is_active) await api.deactivate(agent.id)
      else await api.activate(agent.id)
      onChanged()
    } catch (e) {
      alert((e as Error).message)
    }
  }

  async function runTest() {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await api.testAgent(agent.id)
      if (r.ok) {
        setTestResult(
          r.dim ? `OK · dimensión ${r.dim} · muestra ${r.response ?? '…'}` : `OK · ${r.response ?? 'sin salida'}`
        )
      } else {
        setTestResult(`ERROR · ${friendlyError(r.error ?? 'fallo')}`)
      }
    } catch (e) {
      setTestResult(`ERROR · ${friendlyError((e as Error).message)}`)
    } finally {
      setTesting(false)
    }
  }

  function friendlyError(raw: string): string {
    const tips: Array<[RegExp, string]> = [
      [/RESOURCE_EXHAUSTED|quota exceeded|rate.?limit/i, 'Revisa el plan del proveedor: el modelo puede no estar incluido o agotaste tu cuota.'],
      [/credit balance|insufficient_quota|no credits/i, 'Sin crédito en la cuenta del proveedor: revisa plan y facturación.'],
      [/api key not valid|incorrect api key|invalid_api_key/i, 'La API key no es válida. Edita el agente y pon una clave correcta.']
    ]
    let message = raw.length > 200 ? raw.slice(0, 200) + '…' : raw
    for (const [re, tip] of tips) {
      if (re.test(raw)) return `${message} — ${tip}`
    }
    return message
  }

  async function remove() {
    if (!confirm(`¿Eliminar el agente "${agent.name}"?`)) return
    try {
      await api.deleteAgent(agent.id)
      onChanged()
    } catch (e) {
      alert((e as Error).message)
    }
  }

  return (
    <article className={`card ${agent.is_active ? 'active' : ''}`}>
      <div className="card-head">
        <div>
          <span className={`badge badge-${agent.agent_type}`}>{agent.agent_type_display}</span>
          {agent.is_fallback && <span className="badge badge-fallback">respaldo #{agent.fallback_order}</span>}
          <h3>{agent.name}</h3>
        </div>
        <label className="switch" title={agent.is_active ? 'Activo' : 'Inactivo'}>
          <input type="checkbox" checked={agent.is_active} onChange={toggleActive} />
          <span className="slider"></span>
        </label>
      </div>
      <p className="model">
        {PROVIDER_LABEL[agent.provider] ?? agent.provider} · <code>{agent.model}</code>
        {agent.base_url ? ` · ${agent.base_url}` : ''}
      </p>
      {agent.has_api_key && (
        <p className="key">
          API key <code>{agent.api_key_masked}</code>
        </p>
      )}
      {agent.description && <p className="desc">{agent.description}</p>}
      <dl className="params">
        {agent.agent_type === 'chat' && (
          <>
            <div><dt>temperatura</dt><dd>{agent.temperature}</dd></div>
            <div><dt>max_tokens</dt><dd>{agent.max_tokens}</dd></div>
            <div><dt>top_k</dt><dd>{agent.top_k}</dd></div>
          </>
        )}
        {agent.agent_type === 'embedding' && (
          <>
            <div><dt>dimensión</dt><dd>{agent.embedding_dim}</dd></div>
            <div><dt>top_k</dt><dd>—</dd></div>
          </>
        )}
        {agent.agent_type === 'reranker' && (
          <>
            <div><dt>top_k</dt><dd>{agent.top_k}</dd></div>
          </>
        )}
      </dl>
      <div className="card-actions">
        <button className="ghost" onClick={() => onEdit(agent)}>Editar</button>
        <button className="ghost" onClick={runTest} disabled={testing}>
          {testing ? 'Probando…' : 'Probar'}
        </button>
        <button className="danger" onClick={remove}>Eliminar</button>
      </div>
      {testResult && (
        <p className={`test ${testResult.startsWith('OK') ? 'ok' : 'err'}`} title={testResult}>{testResult}</p>
      )}
    </article>
  )
}
