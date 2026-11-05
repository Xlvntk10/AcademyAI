import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { academyPwa } from './pwa-plugin'
import { readFileSync } from 'node:fs'

const certificate = process.env.ACADEMY_HTTPS_CERT
const privateKey = process.env.ACADEMY_HTTPS_KEY
if (Boolean(certificate) !== Boolean(privateKey)) {
  throw new Error('Set both ACADEMY_HTTPS_CERT and ACADEMY_HTTPS_KEY for local HTTPS.')
}
const https = certificate && privateKey ? { cert: readFileSync(certificate), key: readFileSync(privateKey) } : undefined

export default defineConfig({
  plugins: [react(), academyPwa()],
  server: {
    https,
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  preview: {
    https,
    port: 4173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', globals: true, maxWorkers: 2, testTimeout: 15000 },
})
