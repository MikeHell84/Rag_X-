import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Agent, AgentProvider, AgentType } from '../types'
import {
  EMBEDDING_PROVIDERS,
  KEYLESS_PROVIDERS,
  PROVIDER_KEY_URL,
  PROVIDER_LABEL,
  TYPE_LABEL,
  defaultModel,
  modelsFor
} from '../types'

interface Props {
  agent?: Agent | null
  onClose: () => void
  onSaved: () => void
}

const EMPTY = {
  name: '',
  agent_type: 'chat' as AgentType,
  provider: 'openai' as AgentProvider,
  base_url: '',
  model: 'gpt-4o-mini',
  description: '',
  temperature: 0.2,
  max_tokens: 1024,
  top_k: 5,
  system_prompt: '',
  embedding_dim: 1536,
  api_key: '',
  is_fallback: false,
  fallback_order: 0
}

export default function AgentForm({ agent, onClose, onSaved }: Props) {
  const [form, setForm] = useState(agent ? { ...agent, api_key: '' } : { ...EMPTY })
  const [removeKey, setRemoveKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setForm(agent ? { ...agent, api_key: '' } : { ...EMPTY })
    setRemoveKey(false)
  }, [agent])

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function changeProvider(provider: AgentProvider) {
    setForm((f) => ({
      ...f,
      provider,
      model: defaultModel(provider, f.agent_type)
    }))
  }

  function changeType(agentType: AgentType) {
    setForm((f) => ({
      ...f,
      agent_type: agentType,
      model: defaultModel(f.provider, agentType)
    }))
  }

  async function save() {
    setSaving(true)
    setError(null)
    const needsKey = !KEYLESS_PROVIDERS.includes(form.provider)
    if (!agent && needsKey && !form.api_key?.trim()) {
      setError(
        `Cada agente necesita su propia API key de ${PROVIDER_LABEL[form.provider]}. ` +
          (PROVIDER_KEY_URL[form.provider]
            ? `Obtén una en ${PROVIDER_KEY_URL[form.provider]}`
            : 'Configúrala en el campo «API Key»')
      )
      setSaving(false)
      return
    }
    try {
      const payload: Partial<Agent> = {
        name: form.name.trim(),
        agent_type: form.agent_type,
        provider: form.provider,
        base_url: form.base_url,
        model: form.model.trim(),
        description: form.description,
        temperature: Number(form.temperature),
        max_tokens: Number(form.max_tokens),
        top_k: Number(form.top_k),
        system_prompt: form.system_prompt,
        embedding_dim: Number(form.embedding_dim),
        is_fallback: form.is_fallback,
        fallback_order: Number(form.fallback_order) || 0
      }
      if (form.api_key) payload.api_key = form.api_key
      else if (removeKey) payload.api_key = ''
      if (agent) await api.updateAgent(agent.id, payload)
      else await api.createAgent(payload)
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <h2>{agent ? 'Editar agente' : 'Nuevo agente'}</h2>
          <button className="icon-btn" onClick={onClose}>×</button>
        </header>
        <div className="sheet-body">
          <label>Nombre
            <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Asistente Comercial" />
          </label>
          <label>Tipo
            <select value={form.agent_type} onChange={(e) => changeType(e.target.value as AgentType)}>
              {(Object.keys(TYPE_LABEL) as AgentType[]).map((t) => (
                <option key={t} value={t}>{TYPE_LABEL[t]}</option>
              ))}
            </select>
          </label>
          <div className="row">
            <label>Proveedor
              <select value={form.provider} onChange={(e) => changeProvider(e.target.value as AgentProvider)}>
                {(Object.keys(PROVIDER_LABEL) as AgentProvider[]).map((p) => (
                  <option key={p} value={p}>{PROVIDER_LABEL[p]}</option>
                ))}
              </select>
            </label>
            <label>Modelo
              <input value={form.model} onChange={(e) => set('model', e.target.value)} list="model-list" placeholder="elige o escribe un modelo…" />
              <datalist id="model-list">
                {modelsFor(form.provider, form.agent_type).map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </label>
          </div>
          {form.provider === 'custom' && (
            <label>Base URL
              <input value={form.base_url ?? ''} onChange={(e) => set('base_url', e.target.value)} placeholder="https://api.proveedor.com/v1" />
            </label>
          )}
          {form.provider === 'ollama' && (
            <p className="hint">Ollama corre en local (host.docker.internal:11434). No necesita API key.</p>
          )}
          {form.provider === 'custom' && (
            <p className="hint">Punto de conexión compatible con OpenAI (gateway, LocalAI, Together, etc.).</p>
          )}
          {form.agent_type === 'embedding' && !EMBEDDING_PROVIDERS.includes(form.provider) && (
            <p className="err">Este proveedor no ofrece embeddings; el agente de embeddings solo admite OpenAI, Google, Mistral, Ollama o una API compatible.</p>
          )}
          <label>Descripción
            <input value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="Uso previsto del agente" />
          </label>
          <label>API Key <span className="hint">(exclusiva de este agente · se guarda cifrada)</span>
            <input
              type="password"
              value={form.api_key ?? ''}
              onChange={(e) => {
                set('api_key', e.target.value)
                if (e.target.value) setRemoveKey(false)
              }}
              placeholder={KEYLESS_PROVIDERS.includes(form.provider) ? 'no requiere clave' : `clave de ${PROVIDER_LABEL[form.provider]}`}
              autoComplete="off"
            />
          </label>
          {form.provider !== 'ollama' && (
            <p className="hint">
              Esta clave es <strong>solo de este agente</strong>; no se comparte con otros.
              {!agent && ' Es obligatoria para crearlo.'}
            </p>
          )}
          {PROVIDER_KEY_URL[form.provider] && (
            <p className="hint">
              <a href={PROVIDER_KEY_URL[form.provider]} target="_blank" rel="noreferrer">
                Obtener API key de {PROVIDER_LABEL[form.provider]} ↗
              </a>
            </p>
          )}
          {agent?.has_api_key && (
            <label className="hint">
              Clave guardada: <code>{agent.api_key_masked}</code>
              <label>
                <input type="checkbox" checked={removeKey} onChange={(e) => setRemoveKey(e.target.checked)} />
                Eliminar la clave guardada
              </label>
            </label>
          )}
          <label className="hint">
            <input
              type="checkbox"
              checked={form.is_fallback}
              onChange={(e) => set('is_fallback', e.target.checked)}
            />
            Usar como agente de respaldo (failover)
          </label>
          {form.is_fallback && (
            <label>Orden de respaldo <span className="hint">(0 = primero tras el principal)</span>
              <input
                type="number"
                min="0"
                max="20"
                value={form.fallback_order}
                onChange={(e) => set('fallback_order', Number(e.target.value))}
              />
            </label>
          )}

          {form.agent_type === 'chat' && (
            <>
              <label>Temperatura <span className="hint">{Number(form.temperature).toFixed(2)}</span>
                <input type="range" min="0" max="1.5" step="0.05" value={form.temperature} onChange={(e) => set('temperature', Number(e.target.value))} />
              </label>
              <div className="row">
                <label>Max tokens
                  <input type="number" min="64" max="8192" value={form.max_tokens} onChange={(e) => set('max_tokens', Number(e.target.value))} />
                </label>
                <label>Contextos (top_k)
                  <input type="number" min="1" max="20" value={form.top_k} onChange={(e) => set('top_k', Number(e.target.value))} />
                </label>
              </div>
              <label>Prompt de sistema
                <textarea rows={5} value={form.system_prompt} onChange={(e) => set('system_prompt', e.target.value)} placeholder="Instrucciones para el agente. Usa {contexto} y {pregunta}…" />
              </label>
            </>
          )}
          {form.agent_type === 'embedding' && (
            <label>Dimensión del vector
              <input type="number" min="128" max="3072" value={form.embedding_dim} onChange={(e) => set('embedding_dim', Number(e.target.value))} />
            </label>
          )}
          {form.agent_type === 'reranker' && (
            <label>Top k de re-ranking
              <input type="number" min="1" max="20" value={form.top_k} onChange={(e) => set('top_k', Number(e.target.value))} />
            </label>
          )}
          {error && <p className="err">{error}</p>}
        </div>
        <footer className="sheet-foot">
          <button className="ghost" onClick={onClose}>Cancelar</button>
          <button onClick={save} disabled={saving || !form.name.trim() || !form.model.trim()}>
            {saving ? 'Guardando…' : 'Guardar'}
          </button>
        </footer>
      </div>
    </div>
  )
}
