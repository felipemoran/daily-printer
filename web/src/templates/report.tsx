// Strip 1e of designs/receipt-set-1, on design-system/components/ReportTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, boolean, limitedString, number, object, optional, string, TemplateDataError, type Parser } from './validate'

const amount: Parser<number> = (value, path) => {
  const parsed = number(value, path)
  if (!Number.isFinite(parsed) || parsed < 0) throw new TemplateDataError(`${path}: expected a non-negative number`)
  return parsed
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
  channels: array(object({ label: string, value: amount, prev: amount }), 8),
  days: array(object({ label: string, value: amount }), 7),
})

const format = (value: number) => value.toLocaleString('en-US')

// The largest value spans the full bar; all zeros draw no bars.
const fraction = (value: number, max: number) => (max > 0 ? value / max : 0)
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
            <T.StatTiles columns={2} items={data.kpis} />
          </>
        ) : null}
        {data.channels.length ? (
          <>
            <T.SectionLabel>BY CHANNEL</T.SectionLabel>
            <T.BarList
              rows={data.channels.map(({ label, value, prev }) => ({
                label, value: format(value), a: fraction(value, channelMax), b: fraction(prev, channelMax),
              }))}
              legend={['THIS WEEK', 'LAST WEEK']}
            />
          </>
        ) : null}
        {data.days.length ? (
          <>
            <T.SectionLabel>DAILY VOLUME</T.SectionLabel>
            {/* Columns scales by max(values, 1): fractions make the tallest day full height. */}
            <T.Columns data={data.days.map(({ label, value }) => ({ label, value: fraction(value, dayMax), label2: format(value) }))} />
          </>
        ) : null}
      </>
    )
  },
})
