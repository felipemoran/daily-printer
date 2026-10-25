// Runs a design-system preview unchanged: preview.html?c=<Component>. Only previews that use
// <Paper print> render the #receipt the print pipeline captures (the Tests group does).
import { createRoot } from 'react-dom/client'
import './fonts.css'
import './thermal'

declare global {
  interface Window { ReactDOM: { createRoot: typeof createRoot } }
}

window.ReactDOM = { createRoot }

const previews = import.meta.glob<string>('../../design-system/components/*/preview.html', { query: '?raw', import: 'default' })
const byName = Object.fromEntries(Object.entries(previews).map(([path, load]) => [path.split('/').at(-2)!, load]))
const name = new URLSearchParams(location.search).get('c') ?? ''

if (byName[name]) {
  const html = await byName[name]()
  for (const [, css] of html.matchAll(/<style>([\s\S]*?)<\/style>/g)) {
    document.head.append(Object.assign(document.createElement('style'), { textContent: css }))
  }
  const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1] ?? ''
  new Function(script)()
} else {
  document.getElementById('root')!.textContent =
    `No preview "${name}". Pass ?c=<name>, one of: ${Object.keys(byName).sort().join(', ')}`
}
