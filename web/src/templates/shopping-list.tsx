// The week's shopping list from the mise-en-place site, on design-system/components/TaskRow.
import T from '../thermal'
import { defineTemplate } from './define'
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

const label = { textTransform: 'uppercase' } as const

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => (
    <div style={{ overflowWrap: 'anywhere' }}>
      <T.HeaderBar left="LISTA DE COMPRAS" />
      <T.SectionLabel style={{ marginTop: 20 }}>SEMANA</T.SectionLabel>
      {data.recipes.map((recipe, index) => (
        <div key={index} className="body">
          {recipe.name} · {recipe.portions} {recipe.portions === 1 ? 'porção' : 'porções'}
        </div>
      ))}
      {data.aisles.map((aisle, aisleIndex) => (
        <div key={aisleIndex}>
          <T.SectionLabel style={label}>{aisle.name}</T.SectionLabel>
          {aisle.items.map((item, index) => (
            <T.TaskRow key={index} title={`${item.name} · ${item.amount}`} meta={item.note} />
          ))}
        </div>
      ))}
      {data.pantry.length ? (
        <>
          <T.SectionLabel>DESPENSA</T.SectionLabel>
          <div className="body">{data.pantry.join(' · ')}</div>
        </>
      ) : null}
    </div>
  ),
})
