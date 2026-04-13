import { useEffect, useState } from 'react'
import type { ReceiptPayload, Block, SectionHeaderBlock, DayHeaderBlock, TaskBlock, ReceiptHeaderBlock, ReceiptFooterBlock } from './receiptPayload'
import { CURRENT_SCHEMA_VERSION } from './receiptPayload'
import './App.css'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ok'; data: ReceiptPayload }

function renderReceiptHeader(block: ReceiptHeaderBlock, key: number) {
  return (
    <div key={key} className="receipt-header">
      <div className="receipt-header__date">{block.date}</div>
      <div className="receipt-header__rule" aria-hidden />
    </div>
  )
}

function renderReceiptFooter(block: ReceiptFooterBlock, key: number) {
  return <div key={key} className="receipt-footer">{block.text}</div>
}

function renderSectionHeader(block: SectionHeaderBlock, key: number) {
  const label = block.count != null ? `${block.title} (${block.count})` : block.title
  return <div key={key} className="section-header">{label}</div>
}

function renderDayHeader(block: DayHeaderBlock, key: number) {
  return <div key={key} className="day-header">{block.title}</div>
}

function renderTask(block: TaskBlock, key: number) {
  const metaParts: string[] = []
  if (block.time) metaParts.push(block.time)
  if (block.relative) metaParts.push(block.relative)
  if (block.labels?.length) metaParts.push(block.labels.join(', '))
  const meta = metaParts.join('  ·  ')

  return (
    <div key={key} className="task">
      <div className="task-content">{block.content}</div>
      {meta && <div className="task-meta">{meta}</div>}
    </div>
  )
}

function renderBlock(block: Block, key: number) {
  switch (block.type) {
    case 'receipt_header': return renderReceiptHeader(block, key)
    case 'receipt_footer': return renderReceiptFooter(block, key)
    case 'section_header': return renderSectionHeader(block, key)
    case 'day_header':     return renderDayHeader(block, key)
    case 'task':           return renderTask(block, key)
  }
}

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/payload.json', { cache: 'no-store' })
        if (!res.ok) throw new Error(`payload.json: HTTP ${res.status}`)
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
        setState({ status: 'error', message: e instanceof Error ? e.message : String(e) })
      }
    })()
    return () => { cancelled = true }
  }, [])

  if (state.status === 'loading') {
    return (
      <div id="receipt" className="receipt">
        <p className="muted">Loading…</p>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div id="receipt" className="receipt receipt--error" role="alert">
        <p className="error-title">Payload error</p>
        <pre className="error-body">{state.message}</pre>
      </div>
    )
  }

  return (
    <div id="receipt" className="receipt">
      {state.data.blocks.map((block, i) => renderBlock(block, i))}
    </div>
  )
}

export default App
