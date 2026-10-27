// Shared by the mise-en-place templates, recipe and shopping-list (Claude Design "Kitchen Receipts").
import type { CSSProperties } from 'react'

// The design's rule: "200 ml", "3 × lata" and "½ maço" never split across lines.
export const glue = (text: string) => text.replace(/(\d[\d.,/]*|[½¼¾≈×])\s+/g, '$1\u00A0')

// Display only: the sender's text keeps its case.
export const capitalize = (text: string) => text.replace(/^./u, (first) => first.toLocaleUpperCase('pt-BR'))

export const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

export const portions = (n: number) => count(n, 'porção', 'porções')

const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
const two = (n: number) => String(n).padStart(2, '0')

// The render time in the browser's time zone, which is the server's: "26 out 2026 · 14:08".
export const printedAt = (now = new Date()) =>
  `${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()} · ${two(now.getHours())}:${two(now.getMinutes())}`

export const stepNumber = two

const PAPER = 384
const MIN_TEXT = 14

// A hyphenated compound ("pé-de-moleque") is one word: U+2011 is a hyphen the line cannot break at.
// Archivo draws it as wide as "-".
export const keepHyphens = (text: string) => text.replace(/-/g, '\u2011')

// One size for the whole headline: the design's start size, shrunk until its widest word fits the
// paper. min-content is that word, and it lets CJK break between characters. Only a word too wide
// even at 14px breaks inside itself. Pass the text through keepHyphens. Call it after the faces load.
export function headline(text: string, start: number, ratio: number): CSSProperties {
  const probe = document.createElement('div')
  probe.className = 'rp-d'
  probe.style.cssText = 'position: absolute; visibility: hidden; width: min-content; text-transform: uppercase'
  probe.textContent = text
  document.body.append(probe)
  try {
    const widest = (size: number) => {
      probe.style.fontSize = `${size}px`
      return probe.getBoundingClientRect().width
    }
    const width = widest(start)
    let size = width > PAPER ? Math.max(MIN_TEXT, Math.floor((start * PAPER) / width)) : start
    while (size > MIN_TEXT && widest(size) > PAPER) size -= 1
    const fits = widest(size) <= PAPER
    return { fontSize: size, lineHeight: `${Math.round(size * ratio)}px`, overflowWrap: fits ? 'normal' : 'anywhere' }
  } finally {
    probe.remove()
  }
}

// A row whose items align on mixed fonts can come out a fraction of a dot tall; the rule under it then smears.
export const wholeHeight: CSSProperties = { height: 'calc-size(auto, round(up, size, 1px))' }
export const wholeWidth: CSSProperties = { width: 'calc-size(fit-content, round(up, size, 1px))' }

// A box that follows text inline starts where the text ends, a fraction of a dot in. Shift each
// [data-snap] box right and down by under a dot so its 2-3px stroke lands on whole dots. Relative
// offsets do not move anything else, so one pass is enough. Call it after the faces load.
export function snapToPixels(root: HTMLElement) {
  const origin = root.closest('#receipt')?.getBoundingClientRect() ?? root.getBoundingClientRect()
  const boxes = [...root.querySelectorAll<HTMLElement>('[data-snap]')]
  for (const box of boxes) {
    box.style.position = 'relative'
    box.style.left = box.style.top = '0px'
  }
  const shifts = boxes.map((box) => {
    const { left, top } = box.getBoundingClientRect()
    const x = left - origin.left, y = top - origin.top
    return [Math.ceil(x - 1e-3) - x, Math.ceil(y - 1e-3) - y]
  })
  boxes.forEach((box, index) => {
    box.style.left = `${shifts[index][0]}px`
    box.style.top = `${shifts[index][1]}px`
  })
}
