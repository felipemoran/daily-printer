// A recipe from the mise-en-place site, on design-system/components/RecipeTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, fail, integer, object, oneOf, optional, text, type Parser } from './validate'

// Caps: the mise-en-place catalogue's maxima (2026-10) with about 1.5x headroom. They do not keep
// a full payload under any length: the render's length guard refuses a print that is too long.
const MAX_ITEMS = 35
const MAX_STEPS = 27

const shape = object({
  name: text(64),
  portions: integer(1, 99),
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
    steps: array(object({ verb: text(40), time: optional(text(28)), text: optional(text(210)) }), MAX_STEPS, { min: 1 }),
  }), 8)),
})

type Recipe = ReturnType<typeof shape>

const parse: Parser<Recipe> = (value, path) => {
  const data = shape(value, path)
  if (data.groups.flatMap((group) => group.items).length > MAX_ITEMS) fail(`${path}.groups`, `at most ${MAX_ITEMS} items across all groups`)
  if ((data.phases ?? []).flatMap((phase) => phase.steps).length > MAX_STEPS) fail(`${path}.phases`, `at most ${MAX_STEPS} steps across all phases`)
  return data
}

const KIND = { optional: '(opcional)', base: '(receita base)' }
const subheading = { marginTop: 'var(--space-5)' }
// The timer chip is as wide as its text: round the text box so the chip's edges land on whole pixels.
const whole = { width: 'calc-size(fit-content, round(up, size, 1px))' }

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const phases = data.phases ?? []
    const firstStep = phases.map((_, index) => phases.slice(0, index).reduce((count, phase) => count + phase.steps.length, 1))
    return (
      <div style={{ overflowWrap: 'anywhere' }}>
        <T.HeaderBar left="RECEITA" right={`${data.portions} ${data.portions === 1 ? 'PORÇÃO' : 'PORÇÕES'}`} />
        <div className="display-md" style={{ marginTop: 20, textTransform: 'uppercase', textWrap: 'balance' }}>{data.name}</div>
        <T.Rule weight="bar" style={{ margin: '20px 0 4px' }} />
        <T.SectionLabel style={{ marginTop: 20 }}>INGREDIENTES</T.SectionLabel>
        {data.groups.map((group, groupIndex) => (
          <div key={groupIndex}>
            {group.name ? <div className="body-strong" style={subheading}>{group.name}</div> : null}
            {group.items.map((item, index) => (
              <T.TaskRow
                key={index}
                title={[item.name, item.amount && ` · ${item.amount}`, item.kind && ` ${KIND[item.kind]}`].filter(Boolean).join('')}
              />
            ))}
          </div>
        ))}
        {phases.length ? <T.SectionLabel>PASSOS</T.SectionLabel> : null}
        {phases.map((phase, phaseIndex) => (
          <div key={phaseIndex}>
            {phase.name ? <div className="body-strong" style={subheading}>{phase.name}</div> : null}
            {phase.steps.map((step, index) => (
              <T.Step key={index} n={firstStep[phaseIndex] + index} timer={step.time && <span style={whole}>{step.time}</span>}>
                <b>{step.verb}</b>{step.text ? ` ${step.text}` : null}
              </T.Step>
            ))}
          </div>
        ))}
      </div>
    )
  },
})
