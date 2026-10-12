// The one place that knows the QR encoder: swap the library here.
import qrcode from 'qrcode-generator'
import { limitedString, TemplateDataError, type Parser } from './validate'

const text = limitedString(120)

// The encoder keeps only the low byte of each character, so non-ASCII text encodes wrong.
// 120 ASCII characters fit QR version 7 at level M (45 modules).
export const qrText: Parser<string> = (value, path) => {
  const result = text(value, path)
  if ([...result].some((char) => char.charCodeAt(0) > 0x7f)) throw new TemplateDataError(`${path}: expected ASCII (percent-encode the URL)`)
  return result
}

// Rows of '1'/'0' modules, the shape T.QRSlot's matrix prop takes.
export function qrMatrix(text: string, ecc: 'L' | 'M' | 'Q' | 'H' = 'M'): string[] {
  const code = qrcode(0, ecc)
  code.addData(text)
  code.make()
  const count = code.getModuleCount()
  return Array.from({ length: count }, (_, row) =>
    Array.from({ length: count }, (_, col) => (code.isDark(row, col) ? '1' : '0')).join(''))
}
