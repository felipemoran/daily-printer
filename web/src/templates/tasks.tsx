// Strip 1b of designs/receipt-set-1, on design-system/components/TasksTemplate.
import T from '../thermal'
import { defineTemplate } from './define'
import { array, boolean, integer, object, optional, text } from './validate'

const count = integer(0, 9999)

const parse = object({
  weekday: text(9),
  date: text(9),
  year: text(4),
  // 8 rows at these caps fit one print in W, CJK and emoji.
  tasks: array(object({
    title: text(80),
    meta: optional(text(40)),
    done: optional(boolean),
    priority: optional(text(6)),
  }), 8),
  // Tasks the sender left out to stay under the cap.
  more: optional(count),
  doneYesterday: optional(count),
  printedAt: text(16),
})

export default defineTemplate({
  schemaVersion: 1,
  parse,
  Component: ({ data }) => {
    const open = data.tasks.filter((task) => !task.done)
    const tiles = [{ label: 'OPEN', value: String(open.length + (data.more ?? 0)) }]
    if (data.doneYesterday !== undefined) tiles.push({ label: 'DONE YESTERDAY', value: String(data.doneYesterday) })
    return (
      <>
        <T.Masthead
          title="TASKS"
          aside={[data.weekday, <span key="date" style={{ fontSize: 22 }}>{data.date}</span>, data.year]}
        />
        <div style={{ overflowWrap: 'anywhere' }}>
          {[...open, ...data.tasks.filter((task) => task.done)].map((task, index) => (
            <T.TaskRow key={index} title={task.title} meta={task.meta} done={task.done} tag={task.priority} />
          ))}
        </div>
        {data.more ? <div className="label" style={{ marginTop: 'var(--space-3)' }}>+{data.more} MORE IN TODOIST</div> : null}
        <div style={{ height: 'var(--space-7)' }} />
        <T.StatTiles columns={tiles.length as 1 | 2} valueFirst items={tiles} />
        <div className="rp-foot">printed {data.printedAt} · tear &amp; stick</div>
      </>
    )
  },
})
