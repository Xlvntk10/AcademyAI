import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { academyPwa } from './pwa-plugin'

export default defineConfig({
  plugins: [react(), academyPwa()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', globals: true },
})
