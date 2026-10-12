// Strip 1n of designs/receipt-set-1: a focus ticket to tape to a monitor, on design-system/components/ReminderTemplate.
import { use } from 'react'
import T from '../thermal'
import { defineTemplate } from './define'
import { serverFault } from './faults'
import { integer, object, optional, text } from './validate'

const parse = object({
  id: optional(text(12)),
  title: text(60),
  startedAt: optional(text(10)),
  estimate: optional(text(10)),
  pomodoros: optional(integer(1, 12)),
  noteLines: optional(integer(1, 8)),
  date: text(6),
})

// Largest first. The title takes the first size at which its longest word fits the paper;
// words wrap at spaces. A word too long even for display-sm breaks anywhere.
const TITLE_SIZES = ['display-lg', 'display-md', 'display-sm'] as const
const PAPER_WIDTH = 384

// The title probe must measure Archivo, not a fallback; the mono faces load too so the first commit
// lays out in its final faces.
const FACES = ['900 79px Archivo', '500 18px "IBM Plex Mono"', '700 18px "IBM Plex Mono"']
// A rejection stays cached: a missing face is a build defect, and every focus render then fails with it.
let facesLoading: Promise<void> | undefined
const facesLoaded = () =>
  (facesLoading ??= Promise.all(FACES.map((face) => document.fonts.load(face))).then((loaded) => {
    const missing = FACES.filter((_, index) => !loaded[index].length)
    if (missing.length) throw serverFault(`font ${missing.join(', ')} did not load`)
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
          <span style={{ flex: 'none', whiteSpace: 'nowrap' }}>NOW WORKING ON</span>
          {data.id ? <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{data.id}</span> : null}
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
