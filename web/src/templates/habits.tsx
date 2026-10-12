// Strip 1j of designs/receipt-set-1: a month of habits, one CellGrid row per habit.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, integer, limitedString, object, optional, TemplateDataError, text, type Parser } from './validate'

const wrap = { overflowWrap: 'anywhere', minWidth: 0 } as const

// One character per day: 1 done, 0 missed, - skipped.
const days: Parser<string> = (value, path) => {
  const text = limitedString(31)(value, path)
  if (!/^[01-]{28,31}$/.test(text)) throw new TemplateDataError(`${path}: expected 28 to 31 days of 1, 0 or -`)
  return text
}

const fields = object({
  month: text(12),
  habits: array(object({ name: text(32), days }), 8, { min: 1 }),
  change: optional(object({ points: integer(-100, 100), vs: text(10) })),
})

type Data = ReturnType<typeof fields>

const parse: Parser<Data> = (value, path) => {
  const data = fields(value, path)
  const length = data.habits[0].days.length
  data.habits.forEach(({ days }, index) => {
    if (days.length !== length) {
      throw new TemplateDataError(`${path}.habits[${index}].days: expected ${length} days, like habits[0]`)
    }
  })
  return data
}

const longestRun = (days: string) => Math.max(0, ...days.split(/[0-]/).map((run) => run.length))
const count = (days: string, mark: string) => days.split(mark).length - 1

// Skipped days count neither for nor against completion; the longest run of done days wins, first habit on ties.
// Floored, so 100% means every counted day is done.
const summarize = (habits: Data['habits']) => {
  const best = habits.reduce<{ name?: string; run: number }>(
    (top, { name, days }) => (longestRun(days) > top.run ? { name, run: longestRun(days) } : top), { run: 0 })
  const done = habits.reduce((sum, { days }) => sum + count(days, '1'), 0)
  const counted = habits.reduce((sum, { days }) => sum + days.length - count(days, '-'), 0)
  return { best, completion: counted ? Math.floor((100 * done) / counted) : null }
}

const change = ({ points, vs }: NonNullable<Data['change']>) =>
  `${points > 0 ? '▲ ' : points < 0 ? '▼ ' : ''}${Math.abs(points)} pts vs ${vs}`

const ticks = (length: number) => ['1', '5', '10', '15', '20', '25', String(length)]

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const length = data.habits[0].days.length
    const { best, completion } = summarize(data.habits)
    return (
      <>
        <T.Masthead title={<span style={wrap}>{data.month}</span>} sub={`HABIT LOG · ${length} DAYS`} />
        <div style={{ height: 'var(--space-4)' }} />
        <T.CellGrid
          labelWidth={0}
          spread
          cellWidth={10}
          cellHeight={20}
          rowGap={20}
          ticks={ticks(length)}
          rows={data.habits.map(({ name, days }) => ({
            label: <span style={wrap}>{name}</span>,
            right: `${count(days, '1')}/${length}`,
            cells: days,
          }))}
        />
        <T.Rule weight="rule" style={{ margin: 'var(--space-7) 0 var(--space-4)' }} />
        <T.StatTiles
          columns={2}
          small
          items={[
            {
              label: 'BEST STREAK',
              value: `${best.run} ${best.run === 1 ? 'day' : 'days'}`,
              note: best.name && <span style={wrap}>{best.name}</span>,
            },
            {
              label: 'COMPLETION',
              value: completion === null ? '—' : `${completion}%`,
              note: data.change && <span style={wrap}>{change(data.change)}</span>,
            },
          ]}
        />
      </>
    )
  },
})
