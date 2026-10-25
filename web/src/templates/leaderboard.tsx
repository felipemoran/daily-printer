// Strip 1m of designs/receipt-set-1: #1 as the hero, the rest as bars against a printed quota line.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, object, range, text } from './validate'

const MAX_PEOPLE = 10

// The track shows 0 to 133% of quota, so the quota line sits at 75%: pct * 3 / 400 is exact at 100.
const QUOTA_AT = 0.75

// BarList columns: label, 12px gap, track, 12px gap, 52px value. Its quota mark is centred on QUOTA_X.
const LABEL_WIDTH = 140
const TRACK = 384 - LABEL_WIDTH - 52 - 2 * 12
const QUOTA_PX = Math.round(QUOTA_AT * TRACK)
const QUOTA_X = LABEL_WIDTH + 12 + QUOTA_PX
// BarList rounds 99.7% up onto the quota line; a bar below quota stops one dot short of it.
const fraction = (pct: number) => Math.min(pct >= 100 ? 1 : (QUOTA_PX - 1) / TRACK, (pct * 3) / 400)
const QUOTA_LABEL_WIDTH = 60

const percent = range(0, 1000)

const parse = object({
  title: text(24),
  status: text(12),
  people: array(object({ name: text(24), amount: text(5), pct: percent }), MAX_PEOPLE, { min: 1 }),
  total: object({ amount: text(8), pct: percent }),
})

// Floored: 99.6 must not claim the quota.
const percentText = (pct: number) => `${Math.floor(pct)}%`
const rank = (index: number) => String(index + 1).padStart(2, '0')

const wrap = { overflowWrap: 'anywhere', minWidth: 0 } as const

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const [hero, ...rest] = data.people
    return (
      <>
        <T.HeaderBar left={<span style={wrap}>{data.title}</span>} right={<span style={wrap}>{data.status}</span>} />
        <div style={{ display: 'flex', gap: 'var(--space-5)', alignItems: 'flex-end', marginTop: 'var(--space-6)' }}>
          <div className="display-hero" style={{ flex: 'none' }}>{rank(0)}</div>
          <div style={{ ...wrap, display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <div className="lead" style={wrap}>{hero.name}</div>
            <div className="display-stat">{hero.amount}</div>
            <div className="body-strong">{percentText(hero.pct)} OF QUOTA</div>
          </div>
        </div>
        <T.Rule weight="rule" style={{ margin: 'var(--space-6) 0 var(--space-4)' }} />
        {rest.length ? (
          <>
            <div className="micro" style={{ position: 'relative', height: 21, marginBottom: 'var(--space-2)' }}>
              <span style={{ position: 'absolute', left: QUOTA_X - QUOTA_LABEL_WIDTH / 2, width: QUOTA_LABEL_WIDTH, textAlign: 'center' }}>
                QUOTA
              </span>
            </div>
            <T.BarList
              labelWidth={LABEL_WIDTH}
              marker={QUOTA_AT}
              rows={rest.map(({ name, amount, pct }, index) => ({
                label: (
                  <div style={{ display: 'flex', gap: 'var(--space-2)', whiteSpace: 'normal' }}>
                    <span style={{ flex: 'none' }}>{rank(index + 1)}</span>
                    <span style={wrap}>{name}</span>
                  </div>
                ),
                value: amount,
                a: fraction(pct),
                solid: pct >= 100,
              }))}
            />
            <T.Rule weight="rule" style={{ margin: 'var(--space-6) 0 var(--space-3)' }} />
          </>
        ) : null}
        <div className="body-strong" style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
          <span>TEAM TOTAL</span>
          <span>{data.total.amount} · {percentText(data.total.pct)}</span>
        </div>
      </>
    )
  },
})
