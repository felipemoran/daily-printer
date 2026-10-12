// render.html for src/ticket_templates.py: window.renderTemplate(payload) mounts one template into
// #receipt; window.templateLines(payload) returns its native text lines. Envelope: docs/feature-ticket-templates.md.
/* eslint-disable react-refresh/only-export-components -- entry module: nothing imports it */
import { Component, useEffect, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import './fonts.css'
import T from './thermal'
import type { Template } from './templates/define'
import type { Line } from './templates/textmode-lines'
import { TemplateDataError } from './templates/validate'

declare global {
  interface Window {
    renderTemplate: (payload: unknown) => Promise<void>
    templateLines: (payload: unknown) => Line[]
  }
}

const modules = import.meta.glob<Template<unknown>>('./templates/*.tsx', { eager: true, import: 'default' })
const templates = new Map(Object.entries(modules).map(([path, template]) => [path.slice('./templates/'.length, -'.tsx'.length), template]))

class Boundary extends Component<{ onError: (error: unknown) => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: unknown) { this.props.onError(error) }
  render() { return this.state.failed ? null : this.props.children }
}

// A passive effect after the template's: it runs once the template's own effects (QR canvas) did.
function Committed({ onCommit }: { onCommit: () => void }) {
  useEffect(onCommit, [onCommit])
  return null
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

// ticket_templates.py maps this prefix to RuntimeError: the server failed, not the sender.
const prefixed = (error: unknown) => new Error(`server fault: ${message(error)}`)
const isFault = (error: unknown) => error instanceof Error && error.name === 'ServerFault'

function envelope(payload: unknown): { name: string; template: Template<unknown>; data: unknown } {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error('payload: expected object')
  const { template: name, schemaVersion, data } = payload as Record<string, unknown>
  if (typeof name !== 'string') throw new Error('template: expected string')
  const template = templates.get(name)
  if (!template) throw new Error(`unknown template "${name}"; known: ${[...templates.keys()].sort().join(', ')}`)
  if (schemaVersion !== template.schemaVersion) {
    throw new Error(`template "${name}" expects schemaVersion ${template.schemaVersion}, got ${JSON.stringify(schemaVersion)}`)
  }
  return { name, template, data }
}

// Only a TemplateDataError is the sender's; any other throw from parse is a template bug.
const parseData = (template: Template<unknown>, data: unknown) => {
  try {
    return template.parse(data, 'data')
  } catch (error) {
    throw error instanceof TemplateDataError ? error : prefixed(error)
  }
}

window.templateLines = (payload) => {
  const { name, template, data } = envelope(payload)
  const { lines } = template
  if (!lines) throw new Error(`template "${name}" has no text mode`)
  const parsed = parseData(template, data)
  try {
    return lines(parsed)
  } catch (error) {
    throw prefixed(error)
  }
}

const container = document.getElementById('root')!
let root: Root | null = null

window.renderTemplate = async (payload) => {
  root?.unmount()
  root = null
  const { name, template, data } = envelope(payload)
  const parsed = parseData(template, data)
  root = createRoot(container)
  const mounted = root
  let failure: Error | null = null
  await new Promise<void>((resolve, reject) => {
    mounted.render(
      <T.Paper print data-orientation={template.orientation ?? 'portrait'}>
        <Boundary onError={(error) => { reject(failure = isFault(error) ? prefixed(error) : new Error(`template "${name}" failed to render: ${message(error)}`)) }}>
          <template.Component data={parsed} />
          <Committed onCommit={resolve} />
        </Boundary>
      </T.Paper>,
    )
  })
  // Layout first: font loads start only once laid-out text needs a face.
  void container.offsetHeight
  await document.fonts.ready
  // An effect that throws reaches the boundary after Committed resolved; give React a frame to report it.
  await new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve)))
  if (failure) throw failure
}
