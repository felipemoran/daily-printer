/**
 * Generic block-based receipt payload.
 *
 * JSON written by the gather step and served as /payload.json.
 * The web renderer maps each block type to its visual representation.
 *
 * Designed to be extended: future block types (weather, email, news, etc.)
 * are added as new discriminated union members without breaking existing ones.
 */

// ---------------------------------------------------------------------------
// Block types
// ---------------------------------------------------------------------------

export type SectionHeaderBlock = {
  type: 'section_header'
  /** Display title, e.g. "TODAY — Mon Apr 13" or "OVERDUE" */
  title: string
  /** Optional item count shown in parentheses, e.g. 3 → "OVERDUE (3)" */
  count?: number
}

export type DayHeaderBlock = {
  type: 'day_header'
  /** Human-readable date label, e.g. "Tue Apr 14" */
  title: string
}

export type TaskBlock = {
  type: 'task'
  /** Task title */
  content: string
  /** Formatted time string, e.g. "2:30 PM" or "Apr 1" (for overdue) */
  time?: string
  /** Relative label, e.g. "5 days ago", "yesterday", "tomorrow" */
  relative?: string
  /** Label names, e.g. ["work", "health"] */
  labels?: string[]
}

export type ReceiptHeaderBlock = {
  type: 'receipt_header'
  /** Human-readable date, e.g. "Monday, Apr 13" */
  date: string
}

export type ReceiptFooterBlock = {
  type: 'receipt_footer'
  /** Free-form footer text, e.g. jj change/commit ids */
  text: string
}

// Union of all block types — extend here as new data sources are added.
export type Block = SectionHeaderBlock | DayHeaderBlock | TaskBlock | ReceiptHeaderBlock | ReceiptFooterBlock

// ---------------------------------------------------------------------------
// Top-level payload
// ---------------------------------------------------------------------------

export type ReceiptPayload = {
  schemaVersion: number
  /** ISO 8601 timestamp when the payload was generated */
  generatedAt: string
  blocks: Block[]
}

export const CURRENT_SCHEMA_VERSION = 2
