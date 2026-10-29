import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import path from 'node:path'

// backend (FastAPI :8765) istekleri proxy'lenir: /api, /media, /library, /ws
const backend = 'http://127.0.0.1:8765'
const nm = (p: string) => path.resolve(__dirname, 'node_modules', p)

export default defineConfig({
  plugins: [react()],
  resolve: {
    // remotion-captioneer kendi icinde react 18 / remotion 4.0.438 kopyasi tasiyor: tek kopyaya zorla
    dedupe: ['react', 'react-dom', 'remotion'],
    alias: {
      'captioneer-ui': nm('remotion-captioneer/dist/components/index.js'),
      'captioneer-presets': nm('remotion-captioneer/dist/presets/index.js'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': backend,
      '/media': backend,
      '/library': backend,
      '/ws': { target: backend, ws: true },
    },
  },
})
