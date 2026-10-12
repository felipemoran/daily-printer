// Strip 1c of designs/receipt-set-1, on design-system/components/TicketTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, object, optional, string } from './validate'

const gap = { height: 'var(--space-7)' }

const parse = object({
  kind: optional(string),
  time: optional(string),
  id: string,
  title: string,
  status: object({ from: string, to: string }),
  fields: optional(array(object({ label: string, value: string }))),
  comment: optional(object({ text: string, author: optional(string) })),
})

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => (
    <>
      <T.HeaderBar left={data.kind ?? 'TICKET UPDATE'} right={data.time} />
      <div className="display-xl" style={{ marginTop: 'var(--space-5)', letterSpacing: -1 }}>{data.id}</div>
      <div className="lead" style={{ marginTop: 'var(--space-3)' }}>{data.title}</div>
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
    </>
  ),
})
