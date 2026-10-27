// A recipe from the mise-en-place site: strips 1d-1f of Claude Design "Kitchen Receipts".
import { use, useLayoutEffect, useRef } from 'react'
import T from '../thermal'
import { defineTemplate } from './define'
import { facesLoaded } from './faults'
import { capitalize, glue, headline, keepHyphens, portions, printedAt, snapToPixels, stepNumber, wholeHeight, wholeWidth } from './kitchen'
import { qrMatrix, qrText } from './qr'
import { array, fail, integer, object, oneOf, optional, text, type Parser } from './validate'

// Caps: the mise-en-place catalogue's maxima (2026-10) with about 1.5x headroom. They do not keep
// a full payload under any length: the render's length guard refuses a print that is too long.
// Uses: a cook-mode step references at most 7 ingredients and measures, a recipe 33 in all (madalena).
const MAX_ITEMS = 35
const MAX_STEPS = 27
const MAX_STEP_USES = 10
const MAX_USES = 50

const stepUse = object({ name: text(90), amount: optional(text(16)) })

const shape = object({
  name: text(64),
  portions: integer(1, 99),
  url: qrText,
  groups: array(object({
    name: optional(text(48)),
    items: array(object({
      name: text(90),
      amount: optional(text(16)),
      kind: optional(oneOf('optional', 'base')),
    }), MAX_ITEMS, { min: 1 }),
  }), 6, { min: 1 }),
  phases: optional(array(object({
    name: optional(text(28)),
    steps: array(object({
      verb: text(40),
      time: optional(text(28)),
      text: optional(text(210)),
      uses: optional(array(stepUse, MAX_STEP_USES)),
    }), MAX_STEPS, { min: 1 }),
  }), 8)),
})

type Recipe = ReturnType<typeof shape>

const parse: Parser<Recipe> = (value, path) => {
  const data = shape(value, path)
  const steps = (data.phases ?? []).flatMap((phase) => phase.steps)
  if (data.groups.flatMap((group) => group.items).length > MAX_ITEMS) fail(`${path}.groups`, `at most ${MAX_ITEMS} items across all groups`)
  if (steps.length > MAX_STEPS) fail(`${path}.phases`, `at most ${MAX_STEPS} steps across all phases`)
  if (steps.flatMap((step) => step.uses ?? []).length > MAX_USES) fail(`${path}.phases`, `at most ${MAX_USES} uses across all steps`)
  return data
}

const FACES = ['900 92px Archivo', '500 16px "IBM Plex Mono"', '700 16px "IBM Plex Mono"']

// The design picks the start size by name length.
const titleStyle = (name: string) => {
  const length = [...name].length
  if (length <= 18) return headline(name, 92, 0.84)
  if (length <= 36) return headline(name, 68, 0.86)
  return headline(name, 50, 0.9)
}

const label = { fontWeight: 700, letterSpacing: 3 } as const
const small = { fontSize: 14, lineHeight: '19px' } as const
// 22px tall: it sits on the top of its line so the line keeps its height. Inline-block keeps it on
// one line; only a tag wider than its whole column wraps.
const tag = { display: 'inline-block', verticalAlign: 'top', fontSize: 14, fontWeight: 700, lineHeight: '18px', ...wholeWidth } as const
const KIND = {
  optional: { text: 'OPCIONAL', style: { border: '2px solid #000', padding: '0 5px' } },
  base: { text: 'RECEITA BASE', style: { background: '#000', color: '#fff', padding: '2px 7px' } },
}
const dashed = '2px dashed #000'
// Larger QR codes take 4 dots per module, so a 120-character URL stays about 2 cm wide.
const QR_MAX_FIVE_DOT = 37

// The 4px black gap draws the dividers. Whole-pixel widths, and the INGREDIENTES tile wide enough for its label.
const TRACKS = { 2: '184px 184px', 3: '121px 126px 121px' }

function statTiles(tiles: { label: string; value: number; inverted?: boolean }[]) {
  return (
    <div className="kr-tiles" style={{ display: 'grid', gridTemplateColumns: TRACKS[tiles.length as 2 | 3], gap: 4, background: '#000', border: '4px solid #000', marginTop: 20 }}>
      {tiles.map((tile) => (
        <div key={tile.label} className="kr-tile" style={{ padding: '8px 12px', ...(tile.inverted ? { color: '#fff' } : { background: '#fff' }) }}>
          <div style={{ ...small, fontWeight: 700 }}>{tile.label}</div>
          <div className="rp-d" style={{ fontSize: 64, lineHeight: '64px' }}>{tile.value}</div>
        </div>
      ))}
    </div>
  )
}

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    use(facesLoaded(FACES))
    const root = useRef<HTMLDivElement>(null)
    useLayoutEffect(() => snapToPixels(root.current!))
    const phases = data.phases ?? []
    const firstStep = phases.map((_, index) => phases.slice(0, index).reduce((sum, phase) => sum + phase.steps.length, 1))
    const steps = phases.reduce((sum, phase) => sum + phase.steps.length, 0)
    const items = data.groups.reduce((sum, group) => sum + group.items.length, 0)
    const matrix = qrMatrix(data.url)
    const module = matrix.length > QR_MAX_FIVE_DOT ? 4 : 5, quiet = 4 * module
    const title = keepHyphens(data.name)
    return (
      <div ref={root} style={{ fontSize: 16, lineHeight: '22px', fontWeight: 500, overflowWrap: 'anywhere' }}>
        <div className="rp-d kr-title" style={{ ...titleStyle(title), textTransform: 'uppercase', textWrap: 'balance' }}>{title}</div>
        {statTiles([
          { label: data.portions === 1 ? 'PORÇÃO' : 'PORÇÕES', value: data.portions, inverted: true },
          { label: 'INGREDIENTES', value: items },
          ...(steps ? [{ label: 'PASSOS', value: steps }] : []),
        ])}
        <T.SectionLabel style={{ margin: '24px 0 0' }}>INGREDIENTES</T.SectionLabel>
        {data.groups.map((group, groupIndex) => (
          <div key={groupIndex} className="kr-group" style={{ marginTop: 12 }}>
            {group.name ? (
              <div className="rp-d rp-d-wide kr-group-name" style={{ fontSize: 24, lineHeight: '24px', textTransform: 'uppercase', paddingBottom: 6, textWrap: 'balance' }}>
                {group.name}
              </div>
            ) : null}
            {/* Whole-width amounts start the name column, and a tag that wraps to its start, on a whole dot. */}
            <div className="kr-ingredients" style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', borderTop: '4px solid #000', paddingTop: 4, lineHeight: '22px', ...wholeHeight }}>
              {group.items.map((item, index) => [
                <div key={`a${index}`} className="kr-amount" style={{ padding: '4px 14px 4px 0', fontWeight: 700, whiteSpace: 'nowrap', ...wholeWidth }}>{item.amount}</div>,
                <div key={`n${index}`} className="kr-ingredient" style={{ padding: '4px 0', textWrap: 'pretty' }}>
                  {capitalize(glue(item.name))}
                  {item.kind ? (
                    <span className="kr-kind" data-snap style={{ ...tag, ...KIND[item.kind].style, letterSpacing: 1, marginLeft: 8 }}>{KIND[item.kind].text}</span>
                  ) : null}
                </div>,
              ])}
            </div>
          </div>
        ))}
        {steps ? (
          <>
            <T.Rule weight="bar" style={{ margin: '28px 0 0' }} />
            <T.SectionLabel style={{ margin: '14px 0 0' }}>PASSOS</T.SectionLabel>
          </>
        ) : null}
        {phases.map((phase, phaseIndex) => {
          const first = firstStep[phaseIndex], last = first + phase.steps.length - 1
          return (
            <div key={phaseIndex}>
              {/* An unnamed phase keeps the rule and its range, as an unnamed group keeps its rule. The
                  7px under the name clears a cedilla, as the group head's 6px does. */}
              <div className="kr-phase" style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 14, paddingBottom: 7, borderBottom: '4px solid #000', ...wholeHeight }}>
                <span className="rp-d kr-phase-name" style={{ flex: 1, minWidth: 0, fontSize: 34, lineHeight: '32px', textTransform: 'uppercase', textWrap: 'balance' }}>{phase.name}</span>
                <span className="kr-range" style={{ ...small, fontWeight: 700, whiteSpace: 'nowrap' }}>{first === last ? `passo ${first}` : `passos ${first}–${last}`}</span>
              </div>
              {phase.steps.map((step, index) => (
                <div key={index} className="kr-step" style={{ display: 'grid', gridTemplateColumns: '40px minmax(0, 1fr)', gap: 8, padding: '8px 0', borderBottom: dashed, ...wholeHeight }}>
                  <span className="rp-d kr-step-n" style={{ fontSize: 36, lineHeight: '29px' }}>{stepNumber(first + index)}</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
                    {/* Chrome breaks a cloned verb box as if it had no right padding: reserve that padding here. */}
                    <div className="kr-step-text" style={{ lineHeight: '24px', textWrap: 'pretty', paddingRight: 5 }}>
                      <span className="kr-verb" style={{ background: '#000', color: '#fff', fontWeight: 700, textTransform: 'uppercase', padding: '1px 5px', boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone' }}>{step.verb}</span>
                      {/* Spaces, not margins, separate the run-in: a margin at the end of a full line runs past the paper. */}
                      {step.time ? <>{' '}<span className="kr-time" data-snap style={{ ...tag, border: '2px solid #000', padding: '0 4px', marginTop: 1 }}>{step.time}</span></> : null}
                      {step.text ? ` ${glue(step.text)}` : null}
                    </div>
                    {step.uses?.length ? (
                      <div className="kr-uses" style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: '2px 12px', ...small }}>
                        {step.uses.map((used, useIndex) => [
                          <span key={`a${useIndex}`} className="kr-use-amount" style={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{used.amount}</span>,
                          <span key={`n${useIndex}`} className="kr-use-name" style={{ textWrap: 'pretty' }}>{capitalize(glue(used.name))}</span>,
                        ])}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )
        })}
        <T.Rule weight="bar" style={{ margin: '24px 0 0' }} />
        {/* The QR spec's quiet zone, 4 modules of white on every side: the padding, the gaps, the 24px
            under the rule and the footer's 20px. The text drops under a QR too wide to leave its label one line. */}
        <div className="kr-qr" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: quiet, marginTop: 24, paddingLeft: quiet }}>
          <T.QRSlot matrix={matrix} module={module} quiet={0} />
          <div style={{ flex: '1 1 0', minWidth: 'min-content', display: 'flex', flexDirection: 'column', gap: 6, lineHeight: '24px' }}>
            <span className="kr-qr-label" style={{ ...label, whiteSpace: 'nowrap' }}>RECEITA ONLINE</span>
            <div style={{ lineHeight: '22px', textWrap: 'pretty' }}>Aponte a câmera para abrir a página da receita.</div>
            <div className="kr-url" style={{ ...small, fontWeight: 700, overflowWrap: 'anywhere' }}>{data.url.replace(/^https?:\/\//, '')}</div>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontWeight: 700, marginTop: 20, paddingTop: 10, borderTop: dashed }}>
          <span>BOM APETITE</span><span className="kr-foot-portions" style={{ whiteSpace: 'nowrap' }}>{portions(data.portions).toUpperCase()}</span>
        </div>
        <div className="kr-printed" style={{ ...small, marginTop: 6 }}>impresso em {printedAt()}</div>
      </div>
    )
  },
})
