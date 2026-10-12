import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The Thermal bundle lives in ../design-system.
  server: { fs: { allow: ['..'] } },
  build: {
    rollupOptions: {
      input: { main: 'index.html', thermal: 'thermal.html', preview: 'preview.html' },
    },
  },
})
