import { useEffect, useState } from 'react'
import type { ReceiptPayload } from './receiptPayload'
import { CURRENT_SCHEMA_VERSION } from './receiptPayload'
import './App.css'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ok'; data: ReceiptPayload }

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/payload.json', { cache: 'no-store' })
        if (!res.ok) {
          throw new Error(`payload.json: HTTP ${res.status}`)
        }
        const data = (await res.json()) as ReceiptPayload
        if (typeof data.schemaVersion !== 'number') {
          throw new Error('payload.json: missing schemaVersion')
        }
        if (data.schemaVersion !== CURRENT_SCHEMA_VERSION) {
          throw new Error(
            `payload.json: schemaVersion ${data.schemaVersion} (expected ${CURRENT_SCHEMA_VERSION})`,
          )
        }
        if (cancelled) return
        setState({ status: 'ok', data })
      } catch (e) {
        if (cancelled) return
        const message = e instanceof Error ? e.message : String(e)
        setState({ status: 'error', message })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') {
    return (
      <div id="receipt" className="receipt" role="status">
        <p className="muted">Loading payload…</p>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div id="receipt" className="receipt receipt--error" role="alert">
        <p className="error-title">Receipt payload error</p>
        <pre className="error-body">{state.message}</pre>
      </div>
    )
  }

  const { title, generatedAt, lines } = state.data

  return (
    <div id="receipt" className="receipt">
      <header className="receipt__header">
        <h1 className="receipt__title">{title}</h1>
        <p className="receipt__meta">{generatedAt}</p>
      </header>
      <div className="receipt__rule" aria-hidden />
      <ul className="receipt__lines">
        {lines.map((line, i) => (
          <li key={i} className="receipt__line">
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App
