import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const windowListeners = vi.spyOn(window, 'addEventListener')
const documentListeners = vi.spyOn(document, 'addEventListener')

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('PROD', true)
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('MessageChannel', class {
    port1 = { onmessage: null as ((event: {data: unknown}) => void) | null, close: vi.fn() }
    port2 = { deliver: (data: unknown) => this.port1.onmessage?.({data}) }
  })
})
afterEach(() => {
  for (const [name, listener, options] of windowListeners.mock.calls) window.removeEventListener(name, listener, options)
  for (const [name, listener, options] of documentListeners.mock.calls) document.removeEventListener(name, listener, options)
  windowListeners.mockClear()
  documentListeners.mockClear()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

function installedWorker(controlled = true) {
  const postMessage = vi.fn((_message, ports) => ports[0].deliver({ready: true}))
  const registration = {active:{postMessage}, waiting:null, addEventListener:vi.fn(), update:vi.fn()}
  const events = new EventTarget()
  const serviceWorker = {
    controller: controlled ? registration.active : null,
    getRegistration:vi.fn(async()=>registration),
    register:vi.fn(async()=>{throw new TypeError('server stopped')}),
    addEventListener:events.addEventListener.bind(events),
  }
  vi.stubGlobal('navigator', {serviceWorker})
  return {postMessage, serviceWorker, registration, events}
}

test('installed controller confirms the cached shell even when fetching sw.js fails offline', async () => {
  const {postMessage, serviceWorker} = installedWorker()
  const errors = vi.fn()
  window.addEventListener('academy-pwa-error', errors)
  const pwa = await import('./pwa')
  await pwa.registerPwa()
  expect(serviceWorker.register).toHaveBeenCalledWith('/sw.js', {scope:'/', updateViaCache:'none'})
  expect(postMessage).toHaveBeenCalledWith({type:'CHECK_OFFLINE_SHELL'}, expect.any(Array))
  expect(pwa.offlineShellReady()).toBe(true)
  expect(errors).not.toHaveBeenCalled()
})

test('an active worker does not confirm offline readiness until it controls the document', async () => {
  const {serviceWorker, registration, events, postMessage} = installedWorker(false)
  const pwa = await import('./pwa')
  await pwa.registerPwa()
  expect(pwa.offlineShellReady()).toBe(false)
  expect(postMessage).not.toHaveBeenCalled()
  serviceWorker.controller = registration.active
  events.dispatchEvent(new Event('controllerchange'))
  expect(pwa.offlineShellReady()).toBe(true)
})
