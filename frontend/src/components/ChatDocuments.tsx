import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DocumentDoc, Conversation } from '../types'

type Msg = { role: 'user' | 'assistant' | 'system'; content: string }

function StatusDot({ status }: { status: string }) {
  const color = {
    ready: 'var(--ok)',
    indexed: 'var(--ok)',
    processing: 'var(--accent)',
    failed: 'var(--err)',
    pending: 'var(--warn)'
  }[status] ?? 'var(--muted)'
  return (
    <span className="dot" style={{ background: color, width: 10, height: 10 }} title={status} />
  )
}

function generateSessionKey() {
  return 'sess_' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export default function ChatDocuments() {
  // ---- session / conversation ----
  const [sessionKey] = useState(() => {
    const existing = localStorage.getItem('rag_session_key')
    if (existing) return existing
    const newKey = generateSessionKey()
    localStorage.setItem('rag_session_key', newKey)
    return newKey
  })
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [_conversation] = [conversation] // for future use

  // ---- documentos ----
  const [docs, setDocs] = useState<DocumentDoc[]>([])
  const [count, setCount] = useState<number | null>(null)
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [showUrlForm, setShowUrlForm] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [urlTopic, setUrlTopic] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)

  const loadDocs = () =>
    api
      .documents()
      .then((d) => {
        setDocs(d.results)
        setCount(d.count)
      })
      .finally(() => setLoadingDocs(false))

  const loadConversations = () =>
    api.conversations({ session: sessionKey }).then((c) => setConversations(c.results))

  useEffect(() => {
    loadDocs()
    loadConversations().then(() => {
      if (conversations.length > 0) {
        setConversation(conversations[0])
      }
    })
  }, [])

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg(null)
    try {
      await api.uploadDocument(file)
      setUploadMsg('Subido. La ingesta se encoló y aparecerá en la lista en breve.')
      loadDocs()
    } catch (err) {
      setUploadMsg((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function onUrlSubmit(e: React.FormEvent) {
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
      setUploadMsg((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  // ---- chat ----
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<Msg[]>([])
  const [chatRunning, setChatRunning] = useState(false)
  const [activeConvId, setActiveConvId] = useState<number | null>(null)
  const [reindexing, setReindexing] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollTo({ top: 9999, behavior: 'smooth' })
  }, [history])

  async function ensureConversation() {
    if (activeConvId) return activeConvId
    const title = question.slice(0, 50) || 'Nueva conversación'
    const conv = await api.createConversation({ title, session_key: sessionKey, topic: '' })
    setActiveConvId(conv.id)
    setConversations((prev) => [conv, ...prev])
    return conv.id
  }

  async function saveMessage(role: 'user' | 'assistant', content: string) {
    const convId = await ensureConversation()
    try {
      await api.addMessage(convId, role, content)
    } catch {
      // ignore - local history is source of truth
    }
  }

  async function ask() {
    if (!question.trim() || chatRunning) return
    const q = question.trim()
    setHistory((h) => [...h, { role: 'user', content: q }])
    await saveMessage('user', q)
    setChatRunning(true)
    try {
      const r = await api.createQuery({ question: q })
      if (!r.task_id) throw new Error('No se obtuvo task_id')
      setHistory((h) => [...h, { role: 'assistant', content: 'Procesando…' }])
      let last: any = null
      while (true) {
        await new Promise((t) => setTimeout(t, 1500))
        last = await api.queryResult(r.task_id)
        if (last.status === 'done') {
          const result = last.result
          const answer = typeof result === 'object' ? result?.answer ?? JSON.stringify(result) : String(result)
          setHistory((h) => {
            const copy = [...h]
            copy[copy.length - 1] = { role: 'assistant', content: answer }
            return copy
          })
          await saveMessage('assistant', answer)
          break
        }
        if (last.status === 'error') {
          setHistory((h) => {
            const copy = [...h]
            copy[copy.length - 1] = { role: 'assistant', content: `Error: ${last.error || 'sin detalle'}` }
            return copy
          })
          break
        }
      }
    } catch (e) {
      setHistory((h) => [...h, { role: 'assistant', content: `Error: ${(e as Error).message}` }])
    } finally {
      setChatRunning(false)
      setQuestion('')
    }
  }

  async function loadConversation(conv: Conversation) {
    setConversation(conv)
    setActiveConvId(conv.id)
    if (conv.messages?.length) {
      setHistory(conv.messages.map((m) => ({ role: m.role, content: m.content })))
    } else {
      setHistory([])
    }
    setQuestion('')
  }

  async function newConversation() {
    setConversation(null)
    setActiveConvId(null)
    setHistory([])
    setQuestion('')
  }

  async function deleteConversation(convId: number) {
    if (!window.confirm('Eliminar esta conversación?')) return
    try {
      await api.deleteConversation(convId)
      setConversations((prev) => prev.filter((c) => c.id !== convId))
      if (activeConvId === convId) {
        setActiveConvId(null)
        setConversation(null)
        setHistory([])
      }
    } catch (e) {
      console.error(e)
    }
  }

  async function handleReindex() {
    if (reindexing) return
    setReindexing(true)
    try {
      await api.reindexAll()
      setReindexing(false)
      loadDocs()
    } catch (e) {
      setReindexing(false)
    }
  }

  return (
    <div className="cfg" style={{ gap: 0, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 110px)' }}>
      {/* Upload / URL */}
      <div className="card" style={{ borderRadius: 0, borderBottom: '1px solid var(--border)', padding: 12, gap: 12 }}>
        <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="file" accept=".pdf,.doc,.docx,.md,.txt,.html" onChange={onFile} disabled={uploading} />
            <span className="muted">(arrastre o seleccione un archivo: pdf, docx, md, txt…)</span>
          </label>
          <button className="secondary" onClick={() => setShowUrlForm(!showUrlForm)}>
            {showUrlForm ? '✕' : '🔗'} {' '}Desde URL
          </button>
          {uploadMsg && <p className={uploadMsg.startsWith('Error') ? 'err' : 'ok'} style={{ margin: 0 }}>{uploadMsg}</p>}
        </div>
        {showUrlForm && (
          <form onSubmit={onUrlSubmit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
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
          </form>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', gap: 16, overflow: 'hidden', height: '100%' }}>
        {/* Sidebar: Documentos + Conversaciones */}
        <div style={{ width: '32%', minWidth: 280, display: 'flex', flexDirection: 'column', overflow: 'auto', borderRight: '1px solid var(--border)', paddingRight: 12 }}>
          <div className="toolbar" style={{ marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Documentos ({count ?? docs.length})</h3>
            <button className="secondary" style={{ fontSize: 12, padding: '4px 8px' }} onClick={loadDocs}>🔄</button>
            <button className="secondary" style={{ fontSize: 12, padding: '4px 8px' }} onClick={handleReindex}>🔄 Reindexar todo</button>
          </div>
          {loadingDocs ? (
            <p className="muted">Cargando…</p>
          ) : (
            <table className="doc-table" style={{ fontSize: 13 }}>
              <thead>
                <tr><th style={{ width: 24 }}></th><th>Título</th><th>Estado</th></tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id}>
                    <td><StatusDot status={d.status} /></td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.title}>{d.title}</td>
                    <td>{d.status_display}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="toolbar" style={{ marginTop: 16, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Conversaciones</h3>
            <button className="secondary" style={{ fontSize: 12, padding: '4px 8px' }} onClick={newConversation}>+ Nueva</button>
          </div>
          {conversations.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>Sin conversaciones guardadas</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {conversations.map((c) => (
                <li key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 6, background: activeConvId === c.id ? 'var(--accent)' : 'transparent', borderRadius: 6 }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', fontSize: 13 }} onClick={() => loadConversation(c)}>
                    {c.title || 'Sin título'}
                  </span>
                  <button className="danger" style={{ padding: '2px 6px', fontSize: 11 }} onClick={(e) => { e.stopPropagation(); deleteConversation(c.id) }}>🗑</button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Chat */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div className="toolbar" style={{ marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Chat con el RAG</h3>
            <span className="muted" style={{ fontSize: 12 }}>Sesión: {sessionKey.slice(-8)}</span>
          </div>
          <div
            className="chat-log"
            style={{ flex: 1, overflowY: 'auto', padding: 12, border: '1px solid var(--border)', borderRadius: 10, background: 'var(--panel-2)' }}
          >
            {history.length === 0 ? (
              <p className="muted">Pregunte algo sobre los documentos (ej. "¿Cuál es el nombre legal de Xlerion?")</p>
            ) : (
              history.map((m, i) => (
                <p key={i} style={{ margin: '8px 0', textAlign: m.role === 'user' ? 'right' : 'left' }}>
                  <span style={{ display: 'inline-block', padding: '6px 10px', borderRadius: 8, background: m.role === 'user' ? 'var(--accent)' : 'var(--panel)', color: m.role === 'user' ? '#0b1220' : 'var(--text)' }}>
                    {m.content}
                  </span>
                </p>
              ))
            )}
            <div ref={bottomRef} />
          </div>
          <div className="cfg-actions" style={{ marginTop: 8, gap: 8 }}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && ask()}
              placeholder="Escriba su consulta…"
              disabled={chatRunning}
              style={{ flex: 1 }}
            />
            <button onClick={ask} disabled={chatRunning || !question.trim()}>
              {chatRunning ? 'Enviando…' : 'Enviar'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}