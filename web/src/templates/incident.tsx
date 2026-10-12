// Strip 1d of designs/receipt-set-1, on design-system/components/IncidentTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, object, optional, string, text, type Parser } from './validate'

// The template prints the '#'; a sender's own '#' would print twice.
const incidentId: Parser<string> = (value, path) => text(24)(string(value, path).replace(/^#/, ''), path)

const parse = object({
  severity: text(2),
  id: incidentId,
  openedAt: text(8),
  service: text(40),
  summary: optional(text(80)),
  // The time column is 76 dots wide: 6 characters of 18px mono fit.
  log: optional(array(object({ time: text(6), text: text(80) }), 8)),
  ackBy: text(5),
})

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => (
    // An unbroken token wraps instead of running past the 384-dot edge.
    <div style={{ overflowWrap: 'anywhere' }}>
      <T.HazardTape />
      <div style={{ height: 'var(--space-3)' }} />
      <T.Severity level={data.severity} lines={['INCIDENT', `#${data.id}`, `OPENED ${data.openedAt}`]} />
      <div className="display-sm rp-d-wide" style={{ marginTop: 'var(--space-6)' }}>{data.service}</div>
      {data.summary ? <div className="body-strong" style={{ marginTop: 6 }}>{data.summary}</div> : null}
      {data.log?.length ? (
        <>
          <T.Rule weight="box" style={{ margin: 'var(--space-6) 0 var(--space-4)' }} />
          <T.LogList rows={data.log.map(({ time, text }) => [time, text])} />
        </>
      ) : null}
      <div style={{ height: 'var(--space-7)' }} />
      <T.Callout label={<span>ACK<br />REQUIRED BY</span>} value={data.ackBy} />
      <div style={{ height: 'var(--space-7)' }} />
      <T.HazardTape />
    </div>
  ),
})
