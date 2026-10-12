// The one place that knows the QR encoder: swap the library here.
import qrcode from 'qrcode-generator'

// Rows of '1'/'0' modules, the shape T.QRSlot's matrix prop takes.
export function qrMatrix(text: string, ecc: 'L' | 'M' | 'Q' | 'H' = 'M'): string[] {
  const code = qrcode(0, ecc)
  code.addData(text)
  code.make()
  const count = code.getModuleCount()
  return Array.from({ length: count }, (_, row) =>
    Array.from({ length: count }, (_, col) => (code.isDark(row, col) ? '1' : '0')).join(''))
}
