import { useState } from 'react'
import { api } from '../api'

export default function ChatQuery() {
  const [question, setQuestion] = useState('')
  const [topK, setTopK] = useState(8)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!question.trim() || running) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const q = await api.createQuery({ question: question.trim(), top_k: topK })
      if (!q.task_id) throw new Error('No se obtuvo task_id')
      // Poll de progreso
      setResult({ status: 'processing', task_id: q.task_id })
      let payload: any
      while (true) {
        await new Promise((r) => setTimeout(r, 1500))
        payload = await api.queryResult(q.task_id)
        setResult({ status: payload.status, task_id: q.task_id, result: payload.result, error: payload.error })
        if (payload.status === 'done' || payload.status === 'error') break
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="cfg">
      <p className="muted">Consulta en lenguaje natural sobre los documentos indexados.</p>
      <div className="cfg-grid">
        <label>
          <span className="cfg-key">Pregunta</span>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="ej. ¿Cuál es la política de teletrabajo?"
            disabled={running}
          />
        </label>
        <label>
          <span className="cfg-key">Top K</span>
          <input type="number" min={1} max={50} value={topK} onChange={(e) => setTopK(Number(e.target.value))} disabled={running} />
        </label>
      </div>
      <div className="cfg-actions">
        <button onClick={submit} disabled={running || !question.trim()}>
          {running ? 'Consultando…' : 'Consultar'}
        </button>
      </div>
      {error && <p className="err">Error: {error}</p>}
      {result && result.status === 'processing' && <p className="muted">Procesando tarea {result.task_id}…</p>}
      {result && result.status === 'done' && result.result && (
        <pre className="rag-answer">{JSON.stringify(result.result, null, 2)}</pre>
      )}
      {result && result.status === 'error' && <p className="err">La tarea falló: {result.error || 'sin detalle'}</p>}
    </div>
  )
}
