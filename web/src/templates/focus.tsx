// Strip 1n of designs/receipt-set-1: a focus ticket to tape to a monitor, on design-system/components/ReminderTemplate.
import { use } from 'react'
import T from '../thermal'
import { defineTemplate } from './define'
import { limitedString, number, object, optional, TemplateDataError, type Parser } from './validate'

const count = (min: number, max: number): Parser<number> => (value, path) => {
  const n = number(value, path)
  if (!Number.isInteger(n) || n < min || n > max) throw new TemplateDataError(`${path}: expected an integer from ${min} to ${max}`)
  return n
}

const text = (max: number): Parser<string> => (value, path) => {
  const s = limitedString(max)(value, path)
  if (!s.trim()) throw new TemplateDataError(`${path}: expected non-empty text`)
  return s
}

// id 12 keeps the header on one line beside NOW WORKING ON.
const parse = object({
  id: optional(text(12)),
  title: text(60),
  startedAt: optional(text(10)),
  estimate: optional(text(10)),
  pomodoros: optional(count(1, 12)),
  noteLines: optional(count(1, 8)),
  date: text(6),
})

// Largest first. The title takes the first size at which its longest word fits the paper;
// words wrap at spaces. A word too long even for display-sm breaks anywhere.
const TITLE_SIZES = ['display-lg', 'display-md', 'display-sm'] as const

// Measuring with a fallback face picks the wrong size, so the render suspends until Archivo is in.
let archivo: Promise<void> | undefined
const archivoLoaded = () =>
  (archivo ??= document.fonts.load('900 79px Archivo').then((faces) => {
    if (!faces.length) throw new Error('the Archivo display face did not load')
  }))

// Synchronous, so the committed layout is the measured one: no effect resizes the title later.
function titleSize(text: string) {
  const probe = document.createElement('div')
  probe.style.cssText = 'position: absolute; visibility: hidden; width: var(--paper-width, 384px); text-transform: uppercase'
  probe.textContent = text
  document.body.append(probe)
  try {
    return TITLE_SIZES.find((name) => {
      probe.className = name
      return probe.scrollWidth <= probe.clientWidth
    }) ?? TITLE_SIZES[TITLE_SIZES.length - 1]
  } finally {
    probe.remove()
  }
}

const section = { marginTop: 32 }

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    use(archivoLoaded())
    const meta = [data.startedAt && `started ${data.startedAt}`, data.estimate && `estimate ${data.estimate}`].filter(Boolean).join(' · ')
    return (
      <>
        <div className="label" style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span>NOW WORKING ON</span>
          {data.id ? <span>{data.id}</span> : null}
        </div>
        <T.Rule weight="bar" style={{ margin: '14px 0 18px' }} />
        <div className={titleSize(data.title)} style={{ textTransform: 'uppercase', textWrap: 'balance', overflowWrap: 'anywhere' }}>
          {data.title}
        </div>
        {meta ? <div className="body-strong" style={{ marginTop: 16, overflowWrap: 'anywhere' }}>{meta}</div> : null}
        <T.SectionLabel style={section}>POMODOROS</T.SectionLabel>
        <T.BoxRow count={data.pomodoros ?? 6} columns={6} />
        <T.SectionLabel style={section}>NOTES</T.SectionLabel>
        <T.NoteLines count={data.noteLines ?? 4} />
        <T.TearLine />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 12 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0, overflowWrap: 'anywhere' }}>
            {data.id ? <span className="meta-strong">{data.id}</span> : null}
            <span className="body-strong">{data.title}</span>
            <span className="meta">done at ______ ◯ ◯ ◯</span>
          </div>
          <div className="display-sm" style={{ flex: 'none' }}>{data.date}</div>
        </div>
      </>
    )
  },
})
