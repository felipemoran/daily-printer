export class TemplateDataError extends Error {}

export type Parser<T> = (value: unknown, path: string) => T

const fail = (path: string, expected: string): never => {
  throw new TemplateDataError(`${path}: expected ${expected}`)
}

const primitive = <T>(type: string): Parser<T> => (value, path) =>
  typeof value === type ? (value as T) : fail(path, type)

export const string = primitive<string>('string')
export const number = primitive<number>('number')
export const boolean = primitive<boolean>('boolean')

// Code points, not UTF-16 units: an emoji is one character. src/tasks_template.py clips to match.
export const limitedString = (max: number): Parser<string> => (value, path) =>
  [...string(value, path)].length > max ? fail(path, `at most ${max} characters`) : (value as string)

const ZERO_WIDTH = /[\u200B-\u200D\u2060\uFEFF]/g

// A blank required field would print an empty hero and still report success.
export const nonBlank = (parse: Parser<string>): Parser<string> => (value, path) => {
  const text = parse(value, path)
  return text.replace(ZERO_WIDTH, '').trim() === '' ? fail(path, 'non-blank text') : text
}

export const text = (max: number) => nonBlank(limitedString(max))

export const integer = (min: number, max: number): Parser<number> => (value, path) =>
  Number.isSafeInteger(value) && (value as number) >= min && (value as number) <= max
    ? (value as number)
    : fail(path, `a whole number from ${min} to ${max}`)

export const optional = <T>(parse: Parser<T>): Parser<T | undefined> => (value, path) =>
  value === undefined || value === null ? undefined : parse(value, path)

// max bounds the render time: the page cannot stop a render it has started.
export const array = <T>(item: Parser<T>, max: number, { min = 0 } = {}): Parser<T[]> => (value, path) => {
  if (!Array.isArray(value)) return fail(path, 'array')
  if (value.length < min) return fail(path, `at least ${min} item${min === 1 ? '' : 's'}`)
  if (value.length > max) return fail(path, `at most ${max} items`)
  return value.map((entry, index) => item(entry, `${path}[${index}]`))
}

// Unknown keys are refused so a misspelt optional field fails loudly instead of vanishing.
export const object = <S extends Record<string, Parser<unknown>>>(shape: S): Parser<{ [K in keyof S]: ReturnType<S[K]> }> =>
  (value, path) => {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return fail(path, 'object')
    const record = value as Record<string, unknown>
    const unknown = Object.keys(record).find((key) => !Object.hasOwn(shape, key))
    if (unknown !== undefined) throw new TemplateDataError(`${path}.${unknown}: unknown field`)
    return Object.fromEntries(
      Object.entries(shape).map(([key, parse]) => [key, parse(record[key], `${path}.${key}`)]),
    ) as { [K in keyof S]: ReturnType<S[K]> }
  }
