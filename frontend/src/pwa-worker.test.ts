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

test('worker updates only on request, blocks other tabs, and reports complete shell caching', async () => {
  const handlers: Record<string,(event:any)=>void> = {}
  const skipWaiting = vi.fn(async()=>{})
  let clients = [{url:'http://localhost/#offline'},{url:'http://localhost/#lesson/a2'}]
  const matches = vi.fn(async () => ({ cached:true }))
  const source = readFileSync(new URL('../pwa-worker.js',import.meta.url),'utf8').replace('__VERSION__','test').replace('__PRECACHE__',JSON.stringify(['/index.html','/assets/app.js']))
  runInNewContext(source,{URL,caches:{open:async()=>({match:matches})},self:{skipWaiting,clients:{matchAll:async()=>clients},addEventListener:(name:string,handler:any)=>handlers[name]=handler}})
  let pending: Promise<unknown> | undefined
  const port = {postMessage:vi.fn()}
  const event = {data:{type:'ACTIVATE_UPDATE'},ports:[port],waitUntil:(p:Promise<unknown>)=>pending=p}
  handlers.message(event); await pending
  expect(port.postMessage).toHaveBeenLastCalledWith({status:'other-tabs'})
  expect(skipWaiting).not.toHaveBeenCalled()
  clients = clients.slice(0,1)
  handlers.message(event); await pending
  expect(skipWaiting).toHaveBeenCalledTimes(1)
  handlers.message({...event,data:{type:'CHECK_OFFLINE_SHELL'}}); await pending
  expect(port.postMessage).toHaveBeenLastCalledWith({ready:true})
  matches.mockResolvedValueOnce(undefined as any)
  handlers.message({...event,data:{type:'CHECK_OFFLINE_SHELL'}}); await pending
  expect(port.postMessage).toHaveBeenLastCalledWith({ready:false})
})

test('navigation serves one cached build even when the server returns 503', async () => {
  const handlers: Record<string,(event:any)=>void> = {}
  const network = vi.fn(async()=>({status:503}))
  const shell = {status:200,body:'offline-shell'}
  const source = readFileSync(new URL('../pwa-worker.js',import.meta.url),'utf8').replace('__VERSION__','test').replace('__PRECACHE__','["/index.html"]')
  runInNewContext(source,{URL,fetch:network,caches:{open:async()=>({match:async()=>shell})},self:{location:{origin:'http://localhost'},addEventListener:(name:string,handler:any)=>handlers[name]=handler}})
  let pending: Promise<unknown> | undefined
  handlers.fetch({request:{method:'GET',url:'http://localhost/?launch=home',mode:'navigate'},respondWith:(p:Promise<unknown>)=>pending=p})
  await expect(pending).resolves.toBe(shell)
  expect(network).not.toHaveBeenCalled()
})
