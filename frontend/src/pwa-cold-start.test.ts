// @vitest-environment node
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { expect, test, vi } from 'vitest'

const origin = 'http://localhost:4173'
const paths = ['/index.html', '/assets/app-123.js', '/assets/app-123.css', '/icons/icon-192.png', '/manifest.webmanifest', '/offline.html']
const bodies: Record<string, string> = {
  '/index.html':'<html><script type="module" crossorigin src="/assets/app-123.js"></script><link rel="stylesheet" crossorigin href="/assets/app-123.css"></html>',
  '/assets/app-123.js':'startAcademy()', '/assets/app-123.css':'body{color:green}',
  '/icons/icon-192.png':'PNG', '/manifest.webmanifest':'{"start_url":"/#today"}', '/offline.html':'Восстановление запуска',
}

// Model the Cache API's Vary comparison, which a plain vi.fn() cache misses.
class VaryCache {
  entries = new Map<string, { request: Request; response: Response }>()
  async addAll(urls: string[]) {
    for (const url of urls) this.entries.set(new URL(url, origin).href, {
      request: new Request(new URL(url, origin)),
      response: new Response(bodies[url], {headers:{Vary:'Origin'}}),
    })
  }
  async match(input: string | Request, options: { ignoreVary?: boolean } = {}) {
    const request = typeof input === 'string' ? new Request(new URL(input, origin)) : input
    const entry = this.entries.get(request.url)
    if (!entry) return undefined
    const vary = entry.response.headers.get('vary')?.split(',').map(name => name.trim()) ?? []
    if (!options.ignoreVary && vary.some(name => request.headers.get(name) !== entry.request.headers.get(name))) return undefined
    return entry.response.clone()
  }
}

function boot(cache: VaryCache, network: ReturnType<typeof vi.fn>) {
  const handlers: Record<string, (event: any) => void> = {}
  const source = readFileSync(new URL('../pwa-worker.js',import.meta.url),'utf8')
    .replace('__VERSION__', 'cold-test').replace('__PRECACHE__', JSON.stringify(paths))
  runInNewContext(source, {URL, Response, fetch:network,
    caches:{open:async()=>cache, keys:async()=>['academy-static-cold-test'], delete:vi.fn()},
    self:{location:{origin},clients:{claim:vi.fn(async()=>{})},addEventListener:(name:string, handler:any)=>{handlers[name]=handler}}})
  return handlers
}

test('a fresh worker serves all routes and CORS module assets after the server stops', async () => {
  const persisted = new VaryCache()
  const network = vi.fn(async()=>{throw new Error('servers stopped')})
  const initial = boot(persisted, network)
  let lifetime: Promise<void> | undefined
  initial.install({waitUntil:(promise:Promise<void>)=>{lifetime=promise}})
  await lifetime
  // Reproduce the old miss despite the module being present in Cache Storage.
  const moduleRequest = new Request(origin+'/assets/app-123.js', {headers:{Origin:origin}})
  expect(await persisted.match(moduleRequest)).toBeUndefined()
  const restarted = boot(persisted, network)
  for (const route of ['/today','/learn','/plan','/progress','/','/index.html','/learn?installed=1']) {
    let response: Promise<Response> | undefined
    restarted.fetch({request:{method:'GET',url:origin+route,mode:'navigate'},respondWith:(value:Promise<Response>)=>{response=value}})
    expect(await (await response!).text()).toBe(bodies['/index.html'])
  }
  for (const path of paths.slice(1)) {
    let response: Promise<Response> | undefined
    restarted.fetch({request:new Request(origin+path+'?check=1',{headers:{Origin:origin}}),respondWith:(value:Promise<Response>)=>{response=value}})
    expect(await (await response!).text()).toBe(bodies[path])
  }
  expect(network).not.toHaveBeenCalled()
})

test('missing HTML gives a readable independent fallback instead of a rejected navigation', async () => {
  const cache = new VaryCache()
  await cache.addAll(['/offline.html'])
  const handlers = boot(cache,vi.fn(async()=>{throw new Error('offline')}))
  let response: Promise<Response> | undefined
  handlers.fetch({request:{method:'GET',url:origin+'/plan',mode:'navigate'},respondWith:(value:Promise<Response>)=>{response=value}})
  expect(await (await response!).text()).toBe('Восстановление запуска')
  cache.entries.clear()
  handlers.fetch({request:{method:'GET',url:origin+'/progress',mode:'navigate'},respondWith:(value:Promise<Response>)=>{response=value}})
  expect((await response!).status).toBe(503)
  expect(await (await response!).text()).toContain('Для восстановления оболочки')
})
