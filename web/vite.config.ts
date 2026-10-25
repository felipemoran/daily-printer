import { readdirSync } from 'node:fs'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// dist/templates.json: the template names render.html knows, for src/ticket_templates.py.
// Same rule as the import.meta.glob in src/render-main.tsx: every src/templates/*.tsx.
const templateManifest = (): Plugin => ({
  name: 'template-manifest',
  generateBundle() {
    const names = readdirSync(new URL('./src/templates', import.meta.url))
      .filter((file) => file.endsWith('.tsx'))
      .map((file) => file.slice(0, -'.tsx'.length))
      .sort()
    this.emitFile({ type: 'asset', fileName: 'templates.json', source: JSON.stringify(names) })
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), templateManifest()],
  // The Thermal bundle lives in ../design-system.
  server: { fs: { allow: ['..'] } },
  build: {
    rollupOptions: {
      input: { main: 'index.html', render: 'render.html', preview: 'preview.html' },
    },
  },
})
