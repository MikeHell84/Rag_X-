import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PlatformConfig } from '../types'

export default function PlatformConfigForm() {
  const [config, setConfig] = useState<PlatformConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    api.platformConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  async function save() {
    if (!config) return
    setSaving(true)
    setMsg(null)
    try {
      await api.savePlatformConfig(config)
      setMsg('Configuración guardada y aplicada al pipeline.')
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (!config) return <p className="muted">Cargando configuración…</p>

  const num = (key: keyof PlatformConfig) => (
    <label>
      <span className="cfg-key">{key}</span>
      <input
        type="number"
        min={key === 'use_semantic_guard' ? 0 : 1}
        value={config[key] as number}
        onChange={(e) => setConfig((c) => c && { ...c, [key]: Number(e.target.value) })}
      />
    </label>
  )

  return (
    <div className="cfg">
      <p className="muted">Parámetros globales de recuperación que el pipeline lee en cada ingesta y consulta.</p>
      <div className="cfg-grid">
        {num('chunk_size')}
        {num('chunk_overlap')}
        {num('hybrid_top_k')}
        {num('rerank_top_k')}
        {num('embed_batch_size')}
        {num('max_context_tokens')}
      </div>
      <label className="switch-row">
        <span>Control semántico de corte (embeddings)</span>
        <span className="switch">
          <input
            type="checkbox"
            checked={config.use_semantic_guard}
            onChange={(e) => setConfig((c) => c && { ...c, use_semantic_guard: e.target.checked })}
          />
          <span className="slider"></span>
        </span>
      </label>
      <div className="cfg-actions">
        <button onClick={save} disabled={saving}>{saving ? 'Guardando…' : 'Guardar configuración'}</button>
      </div>
      {msg && <p className={msg.startsWith('Configuración') ? 'ok' : 'err'}>{msg}</p>}
    </div>
  )
}
