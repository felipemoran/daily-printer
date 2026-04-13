/** JSON written by the gather step; must match samples/receipt-sample.json. */

export type ReceiptPayload = {
  schemaVersion: number
  title: string
  generatedAt: string
  lines: string[]
}

export const CURRENT_SCHEMA_VERSION = 1
