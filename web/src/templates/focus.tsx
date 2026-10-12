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

// Characters in the cmap of all three faces under web/public/fonts, less controls, soft hyphen and combining
// marks. Chrome draws any other character from a system face it resolves differently in the page (Times)
// and in the screenshot (Menlo): a Cyrillic id wrapped the header in layout but not on paper, and the PNG
// ended in a band of page canvas.
const UNPRINTABLE = /[^\u0020-\u007E\u00A0-\u00AC\u00AE-\u00FF\u0131\u0152\u0153\u02BC\u02C6\u02DA\u02DC\u2013\u2014\u2018-\u201A\u201C-\u201E\u2022\u2026\u2032\u2033\u2039\u203A\u2044\u20AC\u2122\u2191\u2193\u2212\u2215]/u

const text = (max: number): Parser<string> => (value, path) => {
  const s = limitedString(max)(value, path)
  if (!s.trim()) throw new TemplateDataError(`${path}: expected non-empty text`)
  const unprintable = UNPRINTABLE.exec(s)
  if (unprintable) throw new TemplateDataError(`${path}: expected Latin text; the printer fonts have no "${unprintable[0]}"`)
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
const PAPER_WIDTH = 384

// The title probe must measure Archivo, not a fallback; the mono faces load too so the first commit
// lays out in its final faces.
const FACES = ['900 79px Archivo', '500 18px "IBM Plex Mono"', '700 18px "IBM Plex Mono"']
let facesLoading: Promise<void> | undefined
const facesLoaded = () =>
  (facesLoading ??= Promise.all(FACES.map((face) => document.fonts.load(face))).then(
    (loaded) => {
      const missing = FACES.filter((_, index) => !loaded[index].length)
      if (missing.length) throw new Error(`fonts did not load: ${missing.join(', ')}`)
    },
  ).catch((error: unknown) => {
    facesLoading = undefined
    throw error
  }))

// Synchronous, so the committed layout is the measured one: no effect resizes the title later.
function titleSize(text: string) {
  const probe = document.createElement('div')
  // min-content is the longest word; its bounding width keeps the fraction scrollWidth rounds away.
  probe.style.cssText = 'position: absolute; visibility: hidden; width: min-content; text-transform: uppercase'
  probe.textContent = text
  document.body.append(probe)
  try {
    return TITLE_SIZES.find((name) => {
      probe.className = name
      return probe.getBoundingClientRect().width <= PAPER_WIDTH
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
    use(facesLoaded())
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
