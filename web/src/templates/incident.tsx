// Strip 1d of designs/receipt-set-1, on design-system/components/IncidentTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, limitedString, object, optional } from './validate'

const parse = object({
  severity: limitedString(2),
  id: limitedString(24),
  openedAt: limitedString(8),
  service: limitedString(40),
  summary: optional(limitedString(80)),
  // The time column is 76 dots wide: 6 characters of 18px mono fit.
  log: optional(array(object({ time: limitedString(6), text: limitedString(80) }), 8)),
  ackBy: limitedString(5),
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
