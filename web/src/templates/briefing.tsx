// Strip 1l of designs/receipt-set-1, on the "Morning briefing" pattern in design-system/README.md.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, integer, object, optional, text } from './validate'

// Bounds keep every value inside its fixed-width cell: tests/test_template_briefing.py measures the extremes.
const temperature = integer(-99, 199)
const count = integer(0, 999)

const parse = object({
  weekday: text(12),
  dateLine: text(40),
  weather: optional(object({
    temp: temperature,
    condition: text(24),
    high: temperature,
    low: temperature,
    note: optional(text(40)),
    advice: optional(text(40)),
  })),
  counts: object({ meetings: count, tasks: count, deadlines: count }),
  firstUp: optional(array(object({ time: text(5), title: text(60) }), 3)),
  oneThing: optional(text(140)),
})

const degrees = (value: number) => `${value < 0 ? '−' : ''}${Math.abs(value)}°`

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => (
    <div style={{ overflowWrap: 'anywhere' }}>
      <div className="label" style={{ textAlign: 'center' }}>GOOD MORNING</div>
      <T.Rule weight="double" style={{ margin: 'var(--space-3) 0 var(--space-2)' }} />
      <div className="display-xl" style={{ textAlign: 'center', textWrap: 'balance' }}>{data.weekday}</div>
      <div className="body-strong" style={{ textAlign: 'center', marginTop: 'var(--space-1)' }}>{data.dateLine}</div>
      <T.Rule weight="double" style={{ margin: 'var(--space-3) 0 var(--space-6)' }} />
      {data.weather ? (
        <div style={{ display: 'flex', gap: 'var(--space-6)', alignItems: 'center' }}>
          {/* The text column starts after the hero's fractional glyph width: round it up to a whole pixel.
              The 103px hero line box is odd and the column beside it even: pad to 104 so centring stays whole. */}
          <div className="display-hero" style={{ flex: 'none', width: 'calc-size(max-content, round(up, size, 1px))', paddingBottom: 1 }}>
            {degrees(data.weather.temp)}
          </div>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <span className="lead">{data.weather.condition}</span>
            <span className="body">{`H\u00a0${degrees(data.weather.high)} · L\u00a0${degrees(data.weather.low)}`}</span>
            {data.weather.note ? <span className="body">{data.weather.note}</span> : null}
            {data.weather.advice ? <span className="body-strong">{`→\u00a0${data.weather.advice}`}</span> : null}
          </div>
        </div>
      ) : null}
      <div style={{ marginTop: 'var(--space-7)' }}>
        <T.StatTiles
          columns={3}
          valueFirst
          small
          items={[
            { label: 'MEETINGS', value: String(data.counts.meetings) },
            { label: 'TASKS', value: String(data.counts.tasks) },
            { label: 'DEADLINES', value: String(data.counts.deadlines) },
          ]}
        />
      </div>
      {data.firstUp?.length ? (
        <>
          <T.SectionLabel>FIRST UP</T.SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {data.firstUp.map(({ time, title }, index) => (
              <div key={index} className="body" style={{ display: 'flex', gap: 'var(--space-4)' }}>
                <span className="body-strong" style={{ flex: 'none', width: '5ch' }}>{time}</span>
                <span style={{ flex: 1, minWidth: 0 }}>{title}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}
      {data.oneThing ? (
        <div style={{ marginTop: 'var(--space-7)' }}>
          <T.Callout label="THE ONE THING">{data.oneThing}</T.Callout>
        </div>
      ) : null}
    </div>
  ),
})
