import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import type { Plugin } from 'vite'

export function academyPwa(): Plugin {
  return {
    name: 'academy-local-pwa', apply: 'build', enforce: 'post',
    generateBundle(_options, bundle) {
      const publicFiles = ['manifest.webmanifest', 'icons/academy.svg', 'icons/academy-monochrome.svg', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/maskable-512.png', 'icons/apple-touch-icon.png']
      const paths = [...Object.keys(bundle).filter(name => /\.(js|css|html)$/.test(name)), ...publicFiles]
      const fingerprint = createHash('sha256')
      for (const name of Object.keys(bundle).sort()) {
        const item = bundle[name]
        fingerprint.update(item.type === 'chunk' ? item.code : item.source)
      }
      for (const name of publicFiles) fingerprint.update(readFileSync(new URL(`./public/${name}`, import.meta.url)))
      const template = readFileSync(new URL('./pwa-worker.js', import.meta.url), 'utf8')
      fingerprint.update(template)
      this.emitFile({ type: 'asset', fileName: 'sw.js', source: template.replace('__VERSION__', fingerprint.digest('hex').slice(0,16)).replace('__PRECACHE__', JSON.stringify([...new Set(['/index.html', ...paths.map(name => `/${name}`)])])) })
    },
  }
}
