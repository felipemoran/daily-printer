// Strip 1e of designs/receipt-set-1, on design-system/components/ReportTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, boolean, limitedString, number, object, optional, string, TemplateDataError, type Parser } from './validate'

// Up to 1e12 every amount fits in 4 characters, as compact notation at worst ("1T").
const MAX_AMOUNT = 1e12

const amount: Parser<number> = (value, path) => {
  const parsed = number(value, path)
  if (!(parsed >= 0 && parsed <= MAX_AMOUNT)) throw new TemplateDataError(`${path}: expected a number from 0 to 1e12`)
  // -0 passes the check above and would print as "-0".
  return parsed + 0
}

const week: Parser<number> = (value, path) => {
  const parsed = number(value, path)
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 53) throw new TemplateDataError(`${path}: expected an integer from 1 to 53`)
  return parsed
}

const parse = object({
  week,
  range: string,
  title: string,
  kpis: array(object({ label: string, value: limitedString(6), note: optional(string), inverted: optional(boolean) }), 4),
  channels: array(object({ label: limitedString(7), value: amount, prev: amount }), 8),
  days: array(object({ label: limitedString(4), value: amount }), 7),
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
