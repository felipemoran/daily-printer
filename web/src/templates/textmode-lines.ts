// The build report (strip 1h) as Font A text lines. The raster preview and a native ESC/POS print
// both print these lines, so they break in the same places. No imports: Node runs this file in tests.

export interface BuildReport {
  name?: string
  number: number
  since?: number
  branch: string
  commit: string
  start: string
  duration: string
  status: 'passed' | 'failed'
  stages: { name: string; time: string; status: 'ok' | 'fail' | 'skip' }[]
  suites: { name: string; seconds: number }[]
  failures: { spec: string; reason: string; title: string }[]
  commits: number
  url: string
}

export interface Line {
  text: string
  double?: boolean
  reverse?: boolean
}

export const COLUMNS = 32
export const DOUBLE_COLUMNS = 16

// Which Font A code page holds these is unverified (design-system/verify.md, Text mode). Swap for '#' and '.' if they misprint.
export const BAR = { full: '█', empty: '░', cells: 16 }

export const MORE = '~'

const STATUS = { ok: '[ OK ]', fail: '[FAIL]', skip: '[SKIP]' }

// Output is printable ASCII plus the BAR glyphs; a control character would also break the line on the printer.
const ascii = (text: string) =>
  text.normalize('NFKD').replace(/\p{M}/gu, '').replace(/[^\x20-\x7e]/gu, '?').trim()

const fit = (text: string, width: number) => {
  const flat = ascii(text)
  return flat.length > width ? flat.slice(0, width - 1) + MORE : flat
}

const left = (text: string, width: number) => fit(text, width).padEnd(width)
const right = (text: string, width: number) => fit(text, width).padStart(width)
const center = (text: string, width: number) => {
  const flat = fit(text, width)
  return ' '.repeat(Math.floor((width - flat.length) / 2)) + flat
}

const wrap = (text: string, width: number) => {
  const words = ascii(text).split(/ +/).flatMap((word) => word.match(new RegExp(`.{1,${width}}`, 'g')) ?? [])
  const lines: string[] = []
  for (const word of words) {
    const last = lines.length - 1
    if (last >= 0 && lines[last].length + 1 + word.length <= width) lines[last] += ` ${word}`
    else lines.push(word)
  }
  return lines
}

const two = (value: number) => String(value).padStart(2, '0')

export const formatSeconds = (seconds: number) => {
  const whole = Math.floor(seconds)
  return whole < 3600
    ? `${Math.floor(whole / 60)}:${two(whole % 60)}`
    : `${Math.floor(whole / 3600)}h${two(Math.floor((whole % 3600) / 60))}m`
}

export function buildLines(report: BuildReport): Line[] {
  const rule = (char: string) => char.repeat(COLUMNS)
  const longest = Math.max(0, ...report.suites.map((suite) => suite.seconds))
  const bar = (seconds: number) => {
    const full = longest > 0 ? Math.round((seconds / longest) * BAR.cells) : 0
    return BAR.full.repeat(full) + BAR.empty.repeat(BAR.cells - full)
  }
  const failed = report.status === 'failed'
  const banner = center(failed ? 'BUILD FAILED' : 'BUILD PASSED', DOUBLE_COLUMNS).padEnd(DOUBLE_COLUMNS)

  const text = [
    rule('='),
    center(`${report.name ? `${ascii(report.name).toUpperCase()} ` : ''}BUILD  #${report.number}`, COLUMNS),
    rule('='),
    ` ${left('branch', 6)} ${left(report.branch, 8)} ${left('commit', 6)} ${fit(report.commit, 7)}`,
    ` ${left('start', 6)} ${left(report.start, 8)} ${left('took', 6)} ${fit(report.duration, 7)}`,
    rule('-'),
    ` ${left('STAGE', 16)} ${right('TIME', 5)}  STATUS`,
    ...report.stages.map((stage) => ` ${left(stage.name, 16)} ${right(stage.time, 5)}  ${STATUS[stage.status]}`),
    rule('-'),
  ]
  const after = [
    rule('-'),
    ' SUITE DURATION',
    ...report.suites.map((suite) => ` ${left(suite.name, 6)} ${bar(suite.seconds)} ${right(formatSeconds(suite.seconds), 6)}`),
    rule('-'),
    ` FAILURES (${report.failures.length})`,
    ...report.failures.flatMap((failure) => [
      ` > ${left(failure.spec, 17)} ${right(failure.reason, 10)}`,
      ...wrap(`"${failure.title}"`, COLUMNS - 4).map((line) => `   ${line}`),
    ]),
    rule('-'),
    ` ${fit(`${report.commits} ${report.commits === 1 ? 'commit' : 'commits'}${report.since ? ` since #${report.since}` : ''}`, COLUMNS - 2)}`,
    rule('='),
    ...wrap(report.url, COLUMNS - 2).map((line) => ` ${line}`),
  ]
  const lines: Line[] = [
    ...text.map((line) => ({ text: line })),
    failed ? { text: banner, double: true, reverse: true } : { text: banner, double: true },
    ...after.map((line) => ({ text: line })),
  ]
  // TextMode cuts a longer line without a trace, and the printer would wrap it.
  for (const line of lines) {
    if (line.text.length > (line.double ? DOUBLE_COLUMNS : COLUMNS)) throw new Error(`text-mode line too long: "${line.text}"`)
  }
  return lines
}
