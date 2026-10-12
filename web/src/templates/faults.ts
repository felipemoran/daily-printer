// A failure of the server, not of the sender's data.
export const serverFault = (message: string): Error => Object.assign(new Error(message), { name: 'ServerFault' })

// Keyed by the faces array, so use() gets the same promise on every render. A rejection stays
// cached: a missing face is a build defect, and every render of that template then fails with it.
const loading = new WeakMap<readonly string[], Promise<void>>()

export const facesLoaded = (faces: readonly string[]): Promise<void> => {
  let promise = loading.get(faces)
  if (!promise) {
    promise = Promise.all(faces.map((face) => document.fonts.load(face).catch(() => []))).then((loaded) => {
      const missing = faces.filter((_, index) => !loaded[index].length)
      if (missing.length) throw serverFault(`${missing.length > 1 ? 'fonts' : 'font'} ${missing.join(', ')} did not load`)
    })
    loading.set(faces, promise)
  }
  return promise
}
