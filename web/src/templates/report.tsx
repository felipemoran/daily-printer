// Strip 1e of designs/receipt-set-1, on design-system/components/ReportTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, boolean, integer, object, optional, range, text } from './validate'

// Up to 1e12 every amount fits in 4 characters, as compact notation at worst ("1T").
const amount = range(0, 1e12)

const parse = object({
  week: integer(1, 53),
  // A word of 32 fits the 35-column masthead line with its " ·".
  range: text(32),
  title: text(32),
  // 15 Plex Mono cells fill a 2-up tile.
  kpis: array(object({ label: text(15), value: text(6), note: optional(text(15)), inverted: optional(boolean) }), 4),
  channels: array(object({ label: text(7), value: amount, prev: amount }), 8),
  days: array(object({ label: text(4), value: amount }), 7),
})

// Plex Mono 16px is 9.6px a glyph: 5 fit the 52px BarList value cell, 4 the 46px column of 7 days.
const BAR_VALUE_CHARS = 5
const COLUMN_CHARS = 4

const FORMATS = ([
  { maximumFractionDigits: 2 }, { maximumFractionDigits: 1 }, { maximumFractionDigits: 0 },
  { notation: 'compact', maximumSignificantDigits: 3 }, { notation: 'compact', maximumSignificantDigits: 2 },
  { notation: 'compact', maximumSignificantDigits: 1 },
] as const).map((options) => new Intl.NumberFormat('en-US', options))

// The most precise form that fits: a clipped number would print as a different number.
const fit = (value: number, chars: number) => {
  const texts = FORMATS.map((format) => format.format(value))
  return texts.find((text) => text.length <= chars) ?? texts[texts.length - 1]
}

// The largest value spans the full bar; all zeros draw no bars.
const fraction = (value: number, max: number) => (max > 0 ? value / max : 0)
const sectionGap = { marginTop: 'var(--space-8)' }
// A 3-up tile is 90px wide: too narrow for a 6-character value. An odd count stacks 1-up.
const kpiColumns = (count: number) => (count % 2 ? 1 : 2)
const widest = (values: number[]) => Math.max(0, ...values)

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const channelMax = widest(data.channels.flatMap(({ value, prev }) => [value, prev]))
    const dayMax = widest(data.days.map(({ value }) => value))
    return (
      <>
        <T.Masthead title={`WEEK ${data.week}`} sub={`${data.range} · ${data.title}`} rule={false} />
        {data.kpis.length ? (
          <>
            <div style={{ height: 'var(--space-6)' }} />
            <T.StatTiles columns={kpiColumns(data.kpis.length)} items={data.kpis} />
          </>
        ) : null}
        {data.channels.length ? (
          <>
            <T.SectionLabel style={sectionGap}>BY CHANNEL</T.SectionLabel>
            <T.BarList
              rows={data.channels.map(({ label, value, prev }) => ({
                label, value: fit(value, BAR_VALUE_CHARS), a: fraction(value, channelMax), b: fraction(prev, channelMax),
              }))}
              legend={['THIS WEEK', 'LAST WEEK']}
            />
          </>
        ) : null}
        {data.days.length ? (
          <>
            <T.SectionLabel style={sectionGap}>DAILY VOLUME</T.SectionLabel>
            {/* Columns scales by max(values, 1): fractions make the tallest day full height. */}
            <T.Columns data={data.days.map(({ label, value }) => ({ label, value: fraction(value, dayMax), label2: fit(value, COLUMN_CHARS) }))} />
          </>
        ) : null}
      </>
    )
  },
})
