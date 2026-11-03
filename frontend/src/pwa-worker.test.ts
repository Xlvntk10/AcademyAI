// @vitest-environment node
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { test, expect, vi } from 'vitest'

test('service worker caches only static GETs and leaves API/mutations to the network', async () => {
  const handlers: Record<string,(event:any)=>void> = {}
  const cache = { addAll:vi.fn(async()=>{}),match:vi.fn(async()=>({cached:true})) }
  const source = readFileSync(new URL('../pwa-worker.js',import.meta.url),'utf8').replace('__VERSION__','test').replace('__PRECACHE__',JSON.stringify(['/index.html','/assets/app.js']))
  const network = vi.fn(async()=>{throw Error('offline')})
  runInNewContext(source,{URL,fetch:network,caches:{open:async()=>cache},self:{location:{origin:'http://localhost'},addEventListener:(name:string,handler:any)=>handlers[name]=handler}})
  for (const request of [{method:'GET',url:'http://localhost/api/lessons'},{method:'POST',url:'http://localhost/api/runs'},{method:'GET',url:'https://elsewhere.example/file.js'}]) {
    const respondWith=vi.fn(); handlers.fetch({request,respondWith}); expect(respondWith).not.toHaveBeenCalled()
  }
  let promise: Promise<unknown> | undefined
  handlers.install({waitUntil:(p:Promise<unknown>)=>promise=p}); await promise
  expect(cache.addAll).toHaveBeenCalledWith(['/index.html','/assets/app.js'])
  handlers.fetch({request:{method:'GET',url:'http://localhost/',mode:'navigate'},respondWith:(p:Promise<unknown>)=>promise=p})
  await expect(promise).resolves.toEqual({cached:true})
})
