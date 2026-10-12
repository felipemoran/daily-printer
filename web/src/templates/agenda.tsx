// Strip 1g of designs/receipt-set-1, on the "Agenda to scale" pattern in design-system/README.md.
import { use } from 'react'
import T from '../thermal'
import { defineTemplate } from './define'
import { serverFault } from './faults'
import { array, integer, object, optional, string, TemplateDataError, text, type Parser } from './validate'

const HOUR = 56
const MAX_HOURS = 14
const MIN_EVENT_MINUTES = 10
const GUTTER = 36
const LANE_GAP = 4
const LANE_WIDTH = (384 - GUTTER - LANE_GAP) / 2
const LINE = 22
const NOW_TAG = 'NOW'
const TAG_GAP = 8
// Hour labels and the NOW tick reach 13 dots past the first and last hour lines.
const BLEED = 14
// 384 less the AGENDA masthead (244) and its gap: a longer date wraps.
const DATE_WIDTH = 128
// Right-aligned text starts after a fractional glyph run: round its box so it starts on a whole pixel.
const whole = { width: 'calc-size(fit-content, round(up, size, 1px))' }

type Kind = 'meeting' | 'focus'

const fail = (path: string, message: string): never => {
  throw new TemplateDataError(`${path}: ${message}`)
}

// Minutes since midnight. 24:00 is accepted only where a day can end.
const time = (allowMidnight: boolean): Parser<number> => (value, path) => {
  const clockText = string(value, path)
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(clockText)
  if (match) return Number(match[1]) * 60 + Number(match[2])
  if (allowMidnight && clockText === '24:00') return 24 * 60
  return fail(path, `expected a time HH:MM from 00:00 to ${allowMidnight ? '24:00' : '23:59'}`)
}

const kind: Parser<Kind> = (value, path) =>
  value === 'meeting' || value === 'focus' ? value : fail(path, 'expected "meeting" or "focus"')

const shape = object({
  date: text(12),
  dayStart: integer(0, 23),
  dayEnd: integer(1, 24),
  now: optional(time(false)),
  events: array(object({ start: time(false), end: time(true), title: text(60), kind }), 12),
})

interface Event { start: number; end: number; title: string; kind: Kind; lane: 0 | 1; shared: boolean }
interface Agenda { date: string; dayStart: number; dayEnd: number; now?: number; events: Event[] }

const clock = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`

// Lanes by start time: an event takes the first lane free when it starts. Two lanes hold any day
// where no more than two events overlap at once; a third concurrent event is refused.
const parse: Parser<Agenda> = (value, path) => {
  const data = shape(value, path)
  const day = [data.dayStart * 60, data.dayEnd * 60]
  if (data.dayEnd <= data.dayStart || data.dayEnd - data.dayStart > MAX_HOURS) {
    fail(`${path}.dayEnd`, `expected an hour after dayStart, at most ${MAX_HOURS} hours later`)
  }
  data.events.forEach((event, index) => {
    const at = `${path}.events[${index}]`
    if (event.end - event.start < MIN_EVENT_MINUTES) fail(`${at}.end`, `expected at least ${MIN_EVENT_MINUTES} minutes after start`)
    if (event.start < day[0] || event.end > day[1]) {
      fail(at, `${clock(event.start)}–${clock(event.end)} is outside the day ${clock(day[0])}–${clock(day[1])}`)
    }
  })
  const order = data.events.map((_, index) => index).sort((a, b) => data.events[a].start - data.events[b].start || data.events[a].end - data.events[b].end)
  const laneEnds = [-1, -1]
  const lanes: (0 | 1)[] = []
  for (const index of order) {
    const event = data.events[index]
    const lane = laneEnds.findIndex((end) => end <= event.start)
    if (lane === -1) fail(`${path}.events[${index}]`, `overlaps two other events at ${clock(event.start)}; at most 2 events may overlap`)
    laneEnds[lane] = event.end
    lanes[index] = lane as 0 | 1
  }
  const events = order.map((index) => {
    const event = data.events[index]
    const shared = data.events.some((other, otherIndex) => otherIndex !== index && other.start < event.end && event.start < other.end)
    return { ...event, lane: lanes[index], shared }
  })
  return { ...data, events }
}

// Minutes covered by at least one event: overlaps count once.
const busyMinutes = (events: { start: number; end: number }[]) => {
  let total = 0
  let reach = -1
  for (const { start, end } of [...events].sort((a, b) => a.start - b.start)) {
    if (end > reach) total += end - Math.max(start, reach)
    reach = Math.max(reach, end)
  }
  return total
}

const duration = (minutes: number) => {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return hours && rest ? `${hours}h ${rest}m` : hours ? `${hours}h` : `${rest}m`
}

// A label measured in a fallback face misjudges the fit, so the render suspends until Plex Mono is in.
let plexMono: Promise<void> | undefined
const plexMonoLoaded = () =>
  (plexMono ??= document.fonts.load('700 16px "IBM Plex Mono"').then((faces) => {
    if (!faces.length) throw serverFault('font 700 16px "IBM Plex Mono" did not load')
  }))

// Synchronous, so the committed layout is the measured one. Emoji and CJK come from system faces,
// and only the real text in the real class measures them. Rounded up like the boxes that hold them.
function textWidths(texts: string[]) {
  const probe = document.createElement('div')
  probe.className = 'meta-strong'
  probe.style.cssText = 'position: absolute; visibility: hidden; white-space: nowrap; width: max-content'
  document.body.append(probe)
  try {
    return texts.map((text) => {
      probe.textContent = text
      return Math.ceil(probe.getBoundingClientRect().width)
    })
  } finally {
    probe.remove()
  }
}

const label = (event: Event) => `${clock(event.start)} ${event.title}`

const look = (event: Event, current: boolean) =>
  current ? { border: 0, inset: 0, padding: 8 } : event.kind === 'focus' ? { border: 2, inset: 3, padding: 6 } : { border: 3, inset: 0, padding: 8 }

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    use(plexMonoLoaded())
    const [nowWidth, ...labelWidths] = textWidths([NOW_TAG, ...data.events.map(label)])
    const origin = data.dayStart * 60
    const height = (data.dayEnd - data.dayStart) * HOUR
    // Each edge rounds to the nearest dot on its own, so touching events share an edge exactly.
    const y = (minutes: number) => Math.round(((minutes - origin) * HOUR) / 60)
    const isCurrent = (event: Event) => data.now !== undefined && data.now >= event.start && data.now < event.end
    const boxes = data.events.map((event, index) => {
      const current = isCurrent(event)
      const { border, inset, padding } = look(event, current)
      const top = y(event.start)
      const width = event.shared ? LANE_WIDTH : 384 - GUTTER
      const boxHeight = y(event.end) - top
      const room = width - 2 * (border + inset + padding) - (current ? TAG_GAP + nowWidth : 0)
      const labelled = boxHeight >= 2 * (border + inset) + LINE && labelWidths[index] <= room
      return { event, current, border, inset, padding, top, width, boxHeight, labelled, left: GUTTER + (event.shared ? event.lane * (LANE_WIDTH + LANE_GAP) : 0) }
    })
    const unlabelled = boxes.filter((box) => !box.labelled)
    const busy = busyMinutes(data.events)
    const nowY = data.now !== undefined && data.now >= origin && data.now <= data.dayEnd * 60 ? y(data.now) : null
    const hours = Array.from({ length: data.dayEnd - data.dayStart + 1 }, (_, index) => data.dayStart + index)
    const count = data.events.length
    return (
      <>
        <T.Masthead
          title="AGENDA"
          aside={[<div key="date" style={{ maxWidth: DATE_WIDTH, overflowWrap: 'anywhere' }}>{data.date}</div>, `${count} ${count === 1 ? 'EVENT' : 'EVENTS'}`]}
        />
        <div style={{ padding: `var(--space-5) 0 ${BLEED}px` }}>
          <div style={{ position: 'relative', height }}>
            {hours.map((hour) => (
              <div key={hour} style={{ position: 'absolute', left: 0, right: 0, top: (hour - data.dayStart) * HOUR, borderTop: 'var(--stroke-hair) dashed var(--ink)' }} />
            ))}
            {hours.filter((hour) => (hour - data.dayStart) % 2 === 0).map((hour) => (
              <div key={hour} className="meta-strong" style={{ position: 'absolute', left: 0, width: 26, top: (hour - data.dayStart) * HOUR - 11, background: 'var(--paper)' }}>
                {String(hour).padStart(2, '0')}
              </div>
            ))}
            {nowY !== null ? (
              <>
                <div style={{ position: 'absolute', left: 28, right: 0, top: nowY - 3, height: 6, background: 'var(--ink)' }} />
                <div style={{ position: 'absolute', left: 28, width: 6, top: nowY - 13, height: 26, background: 'var(--ink)' }} />
              </>
            ) : null}
            {boxes.map(({ event, current, border, inset, padding, top, width, boxHeight, labelled, left }, index) => (
              <div
                key={index}
                className="meta-strong"
                style={{
                  position: 'absolute', left, top, width, height: boxHeight, boxSizing: 'border-box', overflow: 'hidden',
                  border: border ? `${border}px solid var(--ink)` : 0,
                  background: current ? 'var(--ink)' : event.kind === 'focus' ? 'var(--tone-50)' : 'var(--paper)',
                  color: current ? 'var(--paper)' : 'var(--ink)',
                  lineHeight: `${LINE}px`, whiteSpace: 'nowrap',
                  padding: current || event.kind !== 'focus' ? `0 ${padding}px` : inset,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: TAG_GAP,
                }}
              >
                {labelled ? (
                  event.kind === 'focus' && !current ? (
                    <span style={{ background: 'var(--paper)', padding: `0 ${padding}px`, ...whole }}>{label(event)}</span>
                  ) : (
                    <>
                      <span>{label(event)}</span>
                      {current ? <span style={whole}>{NOW_TAG}</span> : null}
                    </>
                  )
                ) : null}
              </div>
            ))}
          </div>
        </div>
        {unlabelled.length ? (
          <>
            <T.SectionLabel style={{ margin: 'var(--space-6) 0 var(--space-3)' }}>UNLABELLED</T.SectionLabel>
            <div style={{ overflowWrap: 'anywhere' }}>
              <T.LogList
                timeWidth={120}
                rows={unlabelled.map(({ event }) => [
                  `${clock(event.start)}–${clock(event.end)}`,
                  `${event.kind === 'focus' ? 'FOCUS · ' : ''}${event.title}`,
                ])}
              />
            </div>
          </>
        ) : null}
        <div className="body-strong" style={{ marginTop: 'var(--space-6)', display: 'flex', justifyContent: 'space-between' }}>
          <span>BUSY {duration(busy)}</span>
          <span style={whole}>FREE {duration((data.dayEnd - data.dayStart) * 60 - busy)}</span>
        </div>
      </>
    )
  },
})
