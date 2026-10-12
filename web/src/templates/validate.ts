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

export const limitedString = (max: number): Parser<string> => (value, path) =>
  string(value, path).length > max ? fail(path, `at most ${max} characters`) : (value as string)

export const optional = <T>(parse: Parser<T>): Parser<T | undefined> => (value, path) =>
  value === undefined || value === null ? undefined : parse(value, path)

// max bounds the render time: the page cannot stop a render it has started.
export const array = <T>(item: Parser<T>, max: number): Parser<T[]> => (value, path) => {
  if (!Array.isArray(value)) return fail(path, 'array')
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
