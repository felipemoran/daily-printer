// Strip 1h of designs/receipt-set-1: a CI build report previewed as native 32-column text.
import T from '../thermal'
import { defineTemplate } from './define'
import { buildLines, type BuildReport } from './textmode-lines'
import { array, limitedString, nonBlank, number, object, optional, TemplateDataError, type Parser } from './validate'

const text = (max: number) => nonBlank(limitedString(max))

const oneOf = <V extends string>(...values: V[]): Parser<V> => (value, path) => {
  if (!values.includes(value as V)) throw new TemplateDataError(`${path}: expected one of ${values.join(', ')}`)
  return value as V
}

const count = (min: number, max: number): Parser<number> => (value, path) => {
  const result = number(value, path)
  if (!Number.isInteger(result) || result < min || result > max) throw new TemplateDataError(`${path}: expected a whole number from ${min} to ${max}`)
  return result
}

// 99h59m59s keeps formatSeconds within its 6-column cell.
const seconds: Parser<number> = (value, path) => {
  const result = number(value, path)
  if (!(result >= 0 && result < 360000)) throw new TemplateDataError(`${path}: expected seconds from 0 to 359999`)
  return result
}

// 7 digits keep the title (with a 12-character name) and the commits line within their columns.
const BUILD_MAX = 9_999_999

const parse: Parser<BuildReport> = object({
  name: optional(text(12)),
  number: count(1, BUILD_MAX),
  since: optional(count(1, BUILD_MAX)),
  branch: text(80),
  commit: text(80),
  start: text(40),
  duration: text(40),
  status: oneOf('passed', 'failed'),
  stages: array(object({ name: text(80), time: text(40), status: oneOf('ok', 'fail', 'skip') }), 12),
  suites: array(object({ name: text(80), seconds }), 10),
  failures: array(object({ spec: text(80), reason: text(40), title: text(120) }), 8),
  commits: count(0, BUILD_MAX),
  url: text(200),
})

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => <T.TextMode lines={buildLines(data)} />,
})
