// Strip 1c of designs/receipt-set-1, on design-system/components/TicketTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { qrMatrix, qrText } from './qr'
import { array, object, optional, text } from './validate'

const gap = { height: 'var(--space-7)' }

const parse = object({
  // 24 cells of the header bar fit one line: 16 for kind, 8 for time.
  kind: optional(text(16)),
  time: optional(text(8)),
  id: text(16),
  title: text(120),
  status: object({ from: text(24), to: text(24) }),
  fields: optional(array(object({ label: text(16), value: text(32) }), 10)),
  comment: optional(object({ text: text(280), author: optional(text(32)) })),
  qr: optional(object({ text: qrText, lines: optional(array(text(40), 3)) })),
})

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => (
    // An unbroken token wraps instead of running past the 384-dot edge.
    <div style={{ overflowWrap: 'anywhere' }}>
      <T.HeaderBar left={data.kind ?? 'TICKET UPDATE'} right={data.time} />
      <div className="display-xl" style={{ marginTop: 'var(--space-5)', letterSpacing: -1 }}>{data.id}</div>
      <div className="lead" style={{ marginTop: 'var(--space-3)', textWrap: 'pretty' }}>{data.title}</div>
      <div style={gap} />
      <T.Transition from={data.status.from} to={data.status.to} />
      {data.fields?.length ? (
        <>
          <div style={gap} />
          <T.Leaders rows={data.fields.map(({ label, value }) => [label, value])} />
        </>
      ) : null}
      {data.comment ? (
        <>
          <T.Rule weight="rule" style={{ margin: 'var(--space-7) 0 8px' }} />
          <T.Quote by={data.comment.author}>{data.comment.text}</T.Quote>
        </>
      ) : null}
      {data.qr ? (
        <>
          <T.Rule weight="rule" style={{ margin: 'var(--space-7) 0 var(--space-5)' }} />
          <T.QRSlot matrix={qrMatrix(data.qr.text)} module={3} lines={data.qr.lines} />
        </>
      ) : null}
    </div>
  ),
})
