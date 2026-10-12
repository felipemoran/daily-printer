// Strip 1f of designs/receipt-set-1: a 7-day x 24-hour uptime heatmap on CellGrid.
import T from '../thermal'
import type { CellState } from '../thermal'
import { defineTemplate } from './define'
import { array, limitedString, number, object, optional, TemplateDataError, type Parser } from './validate'

// 51 + 24 * 11 + 23 * 3 = 384: the grid fills the paper on whole pixels.
const LABEL_WIDTH = 51
const CELL_WIDTH = 11
const CELL_GAP = 3
const HOURS = 24

const STATES: Record<string, CellState> = { o: 'empty', d: 'tone', x: 'solid' }

const hours: Parser<CellState[]> = (value, path) => {
  if (typeof value !== 'string' || !/^[odx]{24}$/.test(value)) {
    throw new TemplateDataError(`${path}: expected ${HOURS} characters, each o (ok), d (degraded) or x (down)`)
  }
  return [...value].map((hour) => STATES[hour])
}

const percent: Parser<number> = (value, path) => {
  const result = number(value, path)
  if (!(result >= 0 && result <= 100)) throw new TemplateDataError(`${path}: expected a number from 0 to 100`)
  return result
}

// The label column is 51 dots: five 16px Plex Mono cells. Fallback-font glyphs are wider and would overrun the cells.
const dayLabel: Parser<string> = (value, path) => {
  if (typeof value !== 'string' || !/^[\p{Script=Latin}0-9 ./-]{1,5}$/u.test(value)) {
    throw new TemplateDataError(`${path}: expected 1 to 5 Latin letters, digits, spaces or . / -`)
  }
  return value
}

const days: Parser<{ label: string; hours: CellState[] }[]> = (value, path) => {
  const result = array(object({ label: dayLabel, hours }), 7)(value, path)
  if (result.length === 0) throw new TemplateDataError(`${path}: expected at least 1 item`)
  return result
}

const parse = object({
  service: limitedString(60),
  uptimePct: percent,
  days,
  incidents: optional(array(object({ when: limitedString(9), text: limitedString(80) }), 6)),
})

const wrap = { overflowWrap: 'anywhere' } as const

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const incidents = data.incidents ?? []
    return (
      <>
        <div className="label" style={wrap}>{data.service}</div>
        <div className="display-xl" style={{ marginTop: 'var(--space-2)' }}>{data.uptimePct.toFixed(2)}%</div>
        <div className="body-strong">UPTIME · LAST {data.days.length} {data.days.length === 1 ? 'DAY' : 'DAYS'}</div>
        <T.Rule weight="box" style={{ margin: 'var(--space-6) 0 var(--space-4)' }} />
        <div className="micro" style={{ position: 'relative', height: 21, marginBottom: 6 }}>
          {[0, 6, 12, 18].map((hour) => (
            <span key={hour} style={{ position: 'absolute', left: LABEL_WIDTH + hour * (CELL_WIDTH + CELL_GAP) }}>
              {String(hour).padStart(2, '0')}
            </span>
          ))}
        </div>
        <T.CellGrid
          labelWidth={LABEL_WIDTH}
          cellWidth={CELL_WIDTH}
          gap={CELL_GAP}
          rows={data.days.map((day) => ({ label: day.label, cells: day.hours }))}
          legend={[['empty', 'OK'], ['tone', 'DEGRADED'], ['solid', 'DOWN']]}
        />
        <T.Rule weight="rule" style={{ margin: 'var(--space-6) 0 var(--space-3)' }} />
        <T.SectionLabel style={{ margin: '0 0 var(--space-2)' }}>INCIDENTS ({incidents.length})</T.SectionLabel>
        {incidents.length ? (
          <div style={wrap}>
            <T.LogList timeWidth={98} rows={incidents.map(({ when, text }) => [when, text])} />
          </div>
        ) : null}
      </>
    )
  },
})
