// Strip 1c of designs/receipt-set-1, on design-system/components/TicketTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { qrMatrix, qrText } from './qr'
import { array, nonBlank, object, optional, string } from './validate'

const text = nonBlank(string)

const gap = { height: 'var(--space-7)' }

const parse = object({
  kind: optional(string),
  time: optional(string),
  id: text,
  title: text,
  status: object({ from: text, to: text }),
  fields: optional(array(object({ label: text, value: text }), 10)),
  comment: optional(object({ text, author: optional(string) })),
  qr: optional(object({ text: qrText, lines: optional(array(string, 3)) })),
})

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => (
    <>
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
    </>
  ),
})
