import { useEffect, useState, useRef, useCallback } from 'react'
import { api } from '../api'
import type { DocumentDoc } from '../types'

const STATUS_STAGES: Record<string, number> = {
  pending: 0,
  processing: 25,
  chunked: 50,
  embedded: 75,
  ready: 100,
  failed: 100
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'En cola',
  processing: 'Procesando texto…',
  chunked: 'Fragmentando…',
  embedded: 'Generando embeddings…',
  ready: 'Listo',
  failed: 'Fallido'
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'var(--warn)',
  processing: 'var(--accent)',
  chunked: 'var(--accent-2)',
  embedded: 'var(--ok)',
  ready: 'var(--ok)',
  failed: 'var(--err)'
}

function DocProgress({ doc }: { doc: DocumentDoc }) {
  const pct = STATUS_STAGES[doc.status] ?? 0
  const label = STATUS_LABEL[doc.status] ?? doc.status_display
  const color = STATUS_COLOR[doc.status] ?? 'var(--muted)'
  const isActive = pct < 100

  return (
    <div className="doc-progress">
      <div className="doc-progress-header">
        <span className="doc-progress-dot" style={{ background: color }} />
        <span className="doc-progress-label">{label}</span>
        {isActive && <span className="doc-progress-pct">{pct}%</span>}
      </div>
      <div className="doc-progress-track">
        <div
          className="doc-progress-bar"
          style={{
            width: `${pct}%`,
            background: color,
            animation: isActive ? 'docProgressPulse 1.5s ease-in-out infinite' : 'none'
          }}
        />
      </div>
      {doc.error_message && doc.status === 'failed' && (
        <p className="doc-progress-error">{doc.error_message}</p>
      )}
    </div>
  )
}

export default function DocumentsList() {
  const [docs, setDocs] = useState<DocumentDoc[]>([])
  const [count, setCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [showUrlForm, setShowUrlForm] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [urlTopic, setUrlTopic] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editTopic, setEditTopic] = useState('')
  const [editUrl, setEditUrl] = useState('')
  const [reindexing, setReindexing] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadDocs = useCallback(() =>
    api
      .documents()
      .then((d) => {
        setDocs(d.results)
        setCount(d.count)
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false)),
    []
  )

  useEffect(() => {
    loadDocs()
  }, [loadDocs])

  const hasActive = docs.some((d) => STATUS_STAGES[d.status] !== undefined && STATUS_STAGES[d.status] < 100)

  useEffect(() => {
    if (hasActive) {
      pollRef.current = setInterval(loadDocs, 2000)
    } else if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [hasActive, loadDocs])

  const visible = filter
    ? docs.filter((d) => d.topic === filter)
    : docs

  const topics = Array.from(new Set(docs.map((d) => d.topic))).filter(
    (t): t is string => Boolean(t)
  )

  async function handleDelete(id: number, title: string) {
    if (!window.confirm(`Eliminar "${title}"? Esta acción no se puede deshacer.`)) return
    setUploadMsg('Eliminando…')
    try {
      await api.deleteDocument(id)
      setUploadMsg('Documento eliminado')
      loadDocs()
    } catch (e) {
      setUploadMsg(`Error: ${(e as Error).message}`)
    }
  }

  async function handleReindexAll() {
    if (reindexing) return
    setReindexing(true)
    setUploadMsg('Reindexando todos los documentos…')
    try {
      const res = await api.reindexAll()
      setUploadMsg(`${res.queued} documentos encolados para reindexar`)
      loadDocs()
    } catch (e) {
      setUploadMsg(`Error: ${(e as Error).message}`)
    } finally {
      setReindexing(false)
    }
  }

  async function handleRetry(id: number) {
    setUploadMsg('Reintentando…')
    try {
      await api.retryDocument(id)
      setUploadMsg('Ingesta reencolada')
      loadDocs()
    } catch (e) {
      setUploadMsg(`Error: ${(e as Error).message}`)
    }
  }

  async function handleUrlSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!urlInput.trim()) return
    setUploading(true)
    setUploadMsg('Ingestando URL…')
    try {
      await api.documentFromUrl(urlInput.trim(), urlTopic.trim() || undefined)
      setUploadMsg('URL ingerida. Procesando…')
      setUrlInput('')
      setUrlTopic('')
      setShowUrlForm(false)
      loadDocs()
    } catch (err) {
      setUploadMsg(`Error: ${(err as Error).message}`)
    } finally {
      setUploading(false)
    }
  }

  function startEditing(doc: DocumentDoc) {
    setEditingId(doc.id)
    setEditTitle(doc.title)
    setEditTopic(doc.topic || '')
    setEditUrl(doc.url || '')
  }

  function cancelEditing() {
    setEditingId(null)
    setEditTitle('')
    setEditTopic('')
    setEditUrl('')
  }

  async function handleSave(doc: DocumentDoc) {
    const updates: { title?: string; topic?: string; url?: string } = {}
    if (editTitle !== doc.title) updates.title = editTitle
    if (editTopic !== (doc.topic || '')) updates.topic = editTopic
    if (doc.url && editUrl !== doc.url) updates.url = editUrl
    if (Object.keys(updates).length === 0) {
      cancelEditing()
      return
    }
    setUploadMsg('Guardando…')
    try {
      await api.updateDocument(doc.id, updates)
      setUploadMsg('Documento actualizado')
      loadDocs()
    } catch (e) {
      setUploadMsg(`Error: ${(e as Error).message}`)
    }
    cancelEditing()
  }

  if (loading) return <p className="muted">Cargando documentos…</p>
  if (error) return <p className="err">Error: {error}</p>

  return (
    <div className="cfg">
      <div className="toolbar" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <p className="muted">{count ?? docs.length} documento(s) indexado(s)</p>
        {hasActive && <span className="doc-active-badge">Procesando…</span>}
        <div className="chips">
          <button className={!filter ? 'on' : ''} onClick={() => setFilter('')}>Todos</button>
          {topics.map((t) => (
            <button key={t} className={filter === t ? 'on' : ''} onClick={() => setFilter(t)}>
              {t}
            </button>
          ))}
        </div>
        <button className="secondary" onClick={() => setShowUrlForm(!showUrlForm)}>
          {showUrlForm ? '✕' : '➕'} {' '}Desde URL
        </button>
        <button className="secondary" onClick={handleReindexAll} disabled={reindexing}>
          {reindexing ? '⏳ Reindexando…' : '🔄 Reindexar todo'}
        </button>
      </div>

      {showUrlForm && (
        <form onSubmit={handleUrlSubmit} className="card" style={{ marginBottom: 16, padding: 12, gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input
              type="url"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              placeholder="https://ejemplo.com/articulo"
              required
              style={{ flex: 1, minWidth: 280, padding: 8 }}
            />
            <input
              type="text"
              value={urlTopic}
              onChange={(e) => setUrlTopic(e.target.value)}
              placeholder="Tema (opcional)"
              style={{ width: 180, padding: 8 }}
            />
            <button type="submit" className="primary" disabled={uploading || !urlInput.trim()}>
              {uploading ? 'Procesando…' : 'Ingerir URL'}
            </button>
            <button type="button" className="secondary" onClick={() => setShowUrlForm(false)}>Cancelar</button>
          </div>
          {uploadMsg && <p className={uploadMsg.startsWith('Error') ? 'err' : 'ok'}>{uploadMsg}</p>}
        </form>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="doc-table">
          <thead>
            <tr>
              <th>Progreso</th>
              <th>Título</th>
              <th>Tipo</th>
              <th>Tema</th>
              <th>Chunks</th>
              <th>Tokens</th>
              <th>Actualizado</th>
              <th style={{ width: 140 }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((d) => {
              const isEditing = editingId === d.id
              const isActive = STATUS_STAGES[d.status] !== undefined && STATUS_STAGES[d.status] < 100
              return (
                <tr key={d.id} className={isActive ? 'doc-row-active' : ''}>
                  <td>
                    <DocProgress doc={d} />
                  </td>
                  <td>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        style={{ width: '100%', padding: 4, fontSize: 12 }}
                      />
                    ) : (
                      <span title={d.url ? `URL: ${d.url}` : undefined}>{d.title}</span>
                    )}
                  </td>
                  <td>{d.source_type}</td>
                  <td>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editTopic}
                        onChange={(e) => setEditTopic(e.target.value)}
                        placeholder="(sin tema)"
                        style={{ width: 120, padding: 4, fontSize: 12 }}
                      />
                    ) : (
                      d.topic || '—'
                    )}
                  </td>
                  <td>{d.total_chunks}</td>
                  <td>{d.total_tokens}</td>
                  <td>{new Date(d.updated_at).toLocaleString('es')}</td>
                  <td>
                    {isEditing ? (
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="primary" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleSave(d)}>
                          Guardar
                        </button>
                        <button className="secondary" style={{ padding: '4px 8px', fontSize: 12 }} onClick={cancelEditing}>
                          ✕
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        {d.status === 'failed' && (
                          <button className="secondary" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleRetry(d.id)} title="Reintentar">
                            🔁
                          </button>
                        )}
                        <button className="secondary" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => startEditing(d)} title="Editar">
                          ✎
                        </button>
                        <button className="danger" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => handleDelete(d.id, d.title)} title="Eliminar">
                          🗑
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {visible.length === 0 && <p className="muted">No hay documentos.</p>}
      </div>

      {uploadMsg && !showUrlForm && (
        <p className={uploadMsg.startsWith('Error') ? 'err' : 'ok'} style={{ marginTop: 8 }}>{uploadMsg}</p>
      )}
    </div>
  )
}
