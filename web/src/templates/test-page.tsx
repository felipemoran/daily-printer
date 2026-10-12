// Strip 1a of designs/receipt-set-1: a calibration print of the design system's strokes, tones and type.
import T from '../thermal'
import { defineTemplate } from './define'
import { limitedString, nonBlank, object, optional } from './validate'

const parse = object({
  printer: optional(nonBlank(limitedString(24))),
  printedAt: optional(nonBlank(limitedString(16))),
})

const ROW_HEIGHT = 36

const STROKES: [number, string][] = [
  [1, 'BELOW MIN'],
  [2, 'HAIR'],
  [3, 'RULE'],
  [4, 'BOX'],
  [6, 'HEAVY'],
  [8, 'BAR'],
]

const FILLS: [string, string, string][] = [
  ['solid', 'SOLID', '100%'],
  ['tone-65', 'TONE-65', '65%'],
  ['tone-50', 'TONE-50', '50%'],
  ['tone-35', 'TONE-35', '35%'],
  ['tone-15', 'TONE-15', '15%'],
]

const MONO: [string, string][] = [
  ['micro', '14/700'],
  ['meta', '16/500'],
  ['body', '18/500'],
  ['item', '20/700'],
  ['lead', '21/700'],
]

const section = { margin: 'var(--space-6) 0 var(--space-5)' }
const label = { marginTop: 0 }
const reverse = { background: 'var(--ink)', color: 'var(--paper)', padding: '10px 14px' }

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const sender = [data.printer, data.printedAt].filter(Boolean).join(' · ')
    return (
      <>
        <div className="display-lg">TEST PAGE</div>
        <div className="body-strong" style={{ marginTop: 'var(--space-2)' }}>58MM · 384 DOTS · 8/MM</div>
        {sender ? <div className="meta">{sender}</div> : null}
        <T.Rule weight="bar" style={section} />

        <T.SectionLabel style={label}>LINE WEIGHT</T.SectionLabel>
        {STROKES.map(([height, name]) => (
          <div key={height} className="body" style={{ display: 'flex', gap: 'var(--space-4)', height: ROW_HEIGHT, alignItems: 'center' }}>
            <span style={{ width: 48 }}>{height}PX</span>
            {/* Centre by margin: align-items would put odd strokes on a half pixel. */}
            <span style={{ flex: 1, alignSelf: 'flex-start', height, marginTop: Math.floor((ROW_HEIGHT - height) / 2), background: 'var(--ink)' }} />
            <span style={{ width: 108, textAlign: 'right' }}>{name}</span>
          </div>
        ))}
        <T.Rule weight="rule" style={section} />

        <T.SectionLabel style={label}>FILLS · DITHERED</T.SectionLabel>
        <div className="rp-swatches">
          {FILLS.map(([pattern, name, grey]) => (
            <div key={pattern} className="rp-swatch">
              <div className={`rp-fill-${pattern}`} />
              <div>{name}<br />{grey}</div>
            </div>
          ))}
        </div>
        <T.Rule weight="rule" style={section} />

        <T.SectionLabel style={label}>TYPE SIZE</T.SectionLabel>
        {MONO.map(([style, size]) => (
          <div key={style} className={style}>{size} OPS-2481 resolved</div>
        ))}
        <div className="display-sm" style={{ marginTop: 'var(--space-2)' }}>42 CONDENSED</div>
        <div className="display-md">63 OPS-2481</div>
        <T.Rule weight="rule" style={section} />

        <T.SectionLabel style={label}>REVERSE</T.SectionLabel>
        <div className="body" style={reverse}>18/500 · fills in?</div>
        <div className="body-strong" style={{ ...reverse, marginTop: 'var(--space-2)' }}>18/700 · holds open?</div>

        <T.Rule weight="rule" style={section} />
        <div className="meta">MIN STROKE 2PX · MIN TEXT 16PX</div>
        <div className="meta">MICRO 14PX BOLD · REVERSE 700</div>
      </>
    )
  },
})
