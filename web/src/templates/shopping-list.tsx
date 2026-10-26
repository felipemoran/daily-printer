// The week's shopping list from the mise-en-place site: strips 1a-1c of Claude Design "Kitchen Receipts".
import { use, useLayoutEffect, useRef, type CSSProperties } from 'react'
import T from '../thermal'
import { defineTemplate } from './define'
import { facesLoaded } from './faults'
import { capitalize, count, glue, portions, printedAt, snapToPixels, stepNumber, wholeHeight, wholeWidth } from './kitchen'
import { array, fail, integer, object, optional, text, type Parser } from './validate'

// Caps: the mise-en-place catalogue's maxima (2026-10) with about 1.5x headroom. They do not keep
// a full payload under any length: the render's length guard refuses a print that is too long.
const MAX_ITEMS = 160

const shape = object({
  recipes: array(object({ name: text(64), portions: integer(1, 99) }), 14, { min: 1 }),
  aisles: array(object({
    name: text(30),
    items: array(object({ name: text(90), amount: text(16), note: optional(text(52)) }), MAX_ITEMS, { min: 1 }),
  }), 8),
  pantry: array(text(40), 42),
})

type ShoppingList = ReturnType<typeof shape>

const parse: Parser<ShoppingList> = (value, path) => {
  const data = shape(value, path)
  if (!data.aisles.length && !data.pantry.length) fail(path, 'an aisle or a pantry item')
  if (data.aisles.flatMap((aisle) => aisle.items).length > MAX_ITEMS) fail(`${path}.aisles`, `at most ${MAX_ITEMS} items across all aisles`)
  return data
}

const FACES = ['900 108px Archivo', '600 16px Archivo', '500 16px "IBM Plex Mono"', '700 16px "IBM Plex Mono"']

const label = { fontWeight: 700, letterSpacing: 3 } as const
const small = { fontSize: 14, lineHeight: '19px' } as const

const checkbox = (size: number, style: CSSProperties) => (
  <span className="kr-box" data-snap style={{ flex: 'none', width: size, height: size, boxSizing: 'border-box', border: '3px solid #000', ...style }} />
)

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    use(facesLoaded(FACES))
    const root = useRef<HTMLDivElement>(null)
    useLayoutEffect(() => snapToPixels(root.current!))
    const items = data.aisles.reduce((sum, aisle) => sum + aisle.items.length, 0)
    const summary = [
      count(data.recipes.length, 'receita', 'receitas'), count(items, 'item', 'itens'), count(data.aisles.length, 'corredor', 'corredores'),
    ].join(' · ')
    return (
      <div ref={root} style={{ fontSize: 16, lineHeight: '22px', fontWeight: 500, overflowWrap: 'anywhere' }}>
        <div className="rp-d" style={{ fontSize: 108, lineHeight: '89px' }}>COMPRAS</div>
        <div className="kr-summary" style={{ fontWeight: 700, marginTop: 10 }}>{summary}</div>
        <T.Rule weight="bar" style={{ margin: '16px 0 0' }} />
        <T.SectionLabel style={{ margin: '14px 0 2px' }}>CARDÁPIO</T.SectionLabel>
        {data.recipes.map((recipe, index) => (
          <div key={index} className="kr-menu" style={{ display: 'grid', gridTemplateColumns: '28px minmax(0, 1fr) auto', gap: 10, alignItems: 'baseline', padding: '6px 0', borderBottom: '2px dashed #000', ...wholeHeight }}>
            <span className="rp-d" style={{ fontSize: 22, lineHeight: '22px' }}>{stepNumber(index + 1)}</span>
            <span style={{ fontWeight: 700, lineHeight: '20px', textWrap: 'pretty' }}>{glue(recipe.name)}</span>
            <span className="kr-portions" style={{ ...small, fontWeight: 700, whiteSpace: 'nowrap' }}>{portions(recipe.portions)}</span>
          </div>
        ))}
        {data.pantry.length ? (
          <div className="kr-pantry" style={{ border: '4px solid #000', padding: '10px 12px 12px', marginTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '4px 10px', flexWrap: 'wrap', ...wholeHeight }}>
              <span style={label}>DESPENSA</span>
              <span style={{ ...small, fontWeight: 700 }}>confira antes de sair</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', marginTop: 10 }}>
              {data.pantry.map((name, index) => (
                <span key={index} className="kr-chip" style={{ display: 'flex', gap: 6, alignItems: 'flex-start', minWidth: 0, ...wholeWidth }}>
                  {checkbox(14, { marginTop: 4 })}
                  <span style={{ minWidth: 0 }}>{capitalize(glue(name))}</span>
                </span>
              ))}
            </div>
          </div>
        ) : null}
        {data.aisles.map((aisle, aisleIndex) => (
          <div key={aisleIndex}>
            <div className="rp-d kr-aisle" style={{ marginTop: 16, background: '#000', color: '#fff', padding: '5px 10px 7px', fontSize: 36, lineHeight: '33px', textTransform: 'uppercase', textWrap: 'balance' }}>
              {aisle.name}
            </div>
            {aisle.items.map((item, index) => (
              <div key={index} className="kr-item" style={{ display: 'grid', gridTemplateColumns: '16px minmax(0, 1fr) auto', gap: 10, alignItems: 'start', padding: '3px 0', fontSize: 15, lineHeight: '18px', ...wholeHeight }}>
                {checkbox(16, { marginTop: 1 })}
                <span className="kr-item-name" style={{ textWrap: 'pretty' }}>
                  {capitalize(glue(item.name))}
                  {item.note ? <span className="rp-d kr-note" style={{ fontSize: 16, fontWeight: 600 }}> · {glue(item.note)}</span> : null}
                </span>
                <span className="kr-amount" style={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{item.amount}</span>
              </div>
            ))}
          </div>
        ))}
        <T.Rule weight="bar" style={{ margin: '24px 0 0' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontWeight: 700, marginTop: 10 }}>
          <span>FIM DA LISTA</span><span>BOAS COMPRAS</span>
        </div>
        <div className="kr-printed" style={{ ...small, marginTop: 6 }}>impresso em {printedAt()}</div>
      </div>
    )
  },
})
