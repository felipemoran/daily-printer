// Strip 1k of designs/receipt-set-1: a sprint board printed sideways as a 384-dot-tall banner.
import { defineTemplate } from './define'
import { array, integer, object, text } from './validate'

const BLOCK_WIDTH = 150
const STACK_WIDTH = 240
// Three cards with two-line titles fill the 384 dots under a head; a fourth flows into a second stack.
const CARDS_PER_STACK = 3
const MAX_CARDS = 2 * CARDS_PER_STACK
const MAX_COLUMNS = 6

const card = object({ id: text(12), title: text(24) })

const parse = object({
  sprint: text(12),
  day: integer(1, 99),
  of: integer(1, 99),
  date: text(12),
  columns: array(object({ name: text(10), cards: array(card, MAX_CARDS) }), MAX_COLUMNS, { min: 1 }),
})

const wrap = { overflowWrap: 'anywhere', minWidth: 0 } as const

const stacks = <T,>(items: T[]): T[][] =>
  items.length ? Array.from({ length: Math.ceil(items.length / CARDS_PER_STACK) }, (_, index) =>
    items.slice(index * CARDS_PER_STACK, (index + 1) * CARDS_PER_STACK)) : [[]]

export default defineTemplate({
  schemaVersion: 1,
  orientation: 'landscape',
  parse,
  Component: ({ data }) => {
    const items = data.columns.reduce((total, column) => total + column.cards.length, 0)
    return (
      <div style={{ display: 'flex', gap: 'var(--space-5)', height: 384 }}>
        <div style={{
          flex: 'none', width: BLOCK_WIDTH, boxSizing: 'border-box', padding: 'var(--space-4)',
          background: 'var(--ink)', color: 'var(--paper)',
          display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 'var(--space-3)',
        }}>
          <div className="display-sm" style={wrap}>{data.sprint}</div>
          <div className="meta-strong" style={wrap}>
            <div>DAY {data.day} / {data.of}</div>
            <div>{items} {items === 1 ? 'ITEM' : 'ITEMS'}</div>
            <div>{data.date}</div>
          </div>
        </div>
        {data.columns.map((column, index) => {
          const columnStacks = stacks(column.cards)
          return (
            <div key={index} style={{ flex: 'none', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div className="label" style={{
                display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)',
                paddingBottom: 'var(--space-1)', borderBottom: 'var(--stroke-heavy) solid var(--ink)',
              }}>
                <span style={wrap}>{column.name}</span>
                <span>{column.cards.length}</span>
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
                {columnStacks.map((stack, stackIndex) => (
                  <div key={stackIndex} style={{ width: STACK_WIDTH, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    {stack.map(({ id, title }, cardIndex) => (
                      <div key={cardIndex} className="meta-strong" style={{
                        ...wrap, border: 'var(--stroke-rule) solid var(--ink)', padding: 'var(--space-2) var(--space-3)',
                      }}>
                        <div>{id}</div>
                        <div>{title}</div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    )
  },
})
