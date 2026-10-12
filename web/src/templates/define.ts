// A template is web/src/templates/<name>.tsx with a default export from defineTemplate.
// Helper modules here are .ts so render-main and the templates.json manifest skip them.
import type { ReactNode } from 'react'
import type { Line } from './textmode-lines'
import type { Parser } from './validate'

export interface Template<D> {
  schemaVersion: number
  parse: Parser<D>
  Component: (props: { data: D }) => ReactNode
  // Landscape renders a #receipt 384 dots tall; the pipeline rotates it onto the paper.
  orientation?: 'portrait' | 'landscape'
  // The print as native text (ticket_templates.render_text); Component must preview these lines.
  lines?: (data: D) => Line[]
}

// Declare parse as a const first: an object(...) call inlined here infers D as unknown.
export const defineTemplate = <D>(template: Template<D>): Template<D> => template
