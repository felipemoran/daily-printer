// Strip 1i of designs/receipt-set-1, on design-system/components/PullRequestTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, integer, limitedString, object } from './validate'

// The maxima bound a row to 3 title lines and one line each for number and meta,
// so 20 rows stay under the 4000-dot render cap.
const parse = object({
  prs: array(object({
    number: integer(0, 999_999_999_999),
    title: limitedString(64),
    area: limitedString(10),
    added: integer(0, 999_999),
    removed: integer(0, 999_999),
    ageDays: integer(0, 9999),
  }), 20),
})

const STALE_AFTER_DAYS = 2
const age = (days: number) => `${days}D`

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data: { prs } }) => (
    <>
      <div className="display-md">REVIEW<br />QUEUE</div>
      <div className="body-strong" style={{ marginTop: 'var(--space-3)' }}>
        {prs.length} WAITING ON YOU
        {prs.length ? ` · OLDEST ${age(Math.max(...prs.map((pr) => pr.ageDays)))}` : null}
      </div>
      <T.Rule weight="bar" style={{ margin: 'var(--space-5) 0 0' }} />
      {prs.length ? null : <div className="body" style={{ padding: 'var(--space-4) 0' }}>NOTHING TO REVIEW</div>}
      {prs.toSorted((a, b) => b.ageDays - a.ageDays).map((pr, index) => (
        <div key={index}>
          <div style={{ padding: 'var(--space-4) 0', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="item">#{pr.number}</span>
              {pr.ageDays > STALE_AFTER_DAYS
                ? <T.Tag>STALE {age(pr.ageDays)}</T.Tag>
                : <T.Tag variant="outline">{age(pr.ageDays)}</T.Tag>}
            </div>
            <div className="body-strong" style={{ textWrap: 'pretty', overflowWrap: 'anywhere' }}>{pr.title}</div>
            <div className="meta" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-3)' }}>
              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{pr.area} · +{pr.added} −{pr.removed}</span>
              <T.DiffGlyph added={pr.added} removed={pr.removed} />
            </div>
          </div>
          <T.Rule weight="hair" style={{ margin: 0 }} />
        </div>
      ))}
    </>
  ),
})
