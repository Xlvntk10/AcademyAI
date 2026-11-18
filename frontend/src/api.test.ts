import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError } from './api'
vi.mock('./account-context', () => ({accountUser: () => null, canConnect: () => true}))
afterEach(() => vi.unstubAllGlobals())

test('a host wake-up page or a broken rewrite cannot masquerade as API success', async () => {
  const fetch = vi.fn(async () => new Response('<html>Host starting</html>', {status:200, headers:{'Content-Type':'text/html'}}))
  vi.stubGlobal('fetch', fetch)
  await expect(api('/auth/session')).rejects.toMatchObject({status:503})
  await expect(api('/auth/session')).rejects.toThrow('Повтори подключение через минуту')
  expect(fetch).toHaveBeenCalledWith('/api/auth/session', expect.objectContaining({credentials:'same-origin',cache:'no-store'}))
})

test('failed login exposes only a generic message, not an upstream error page', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>PRIVATE diagnostic</html>', {status:502})))
  const error = await api('/auth/verify', {email:'learner@example.test', code:'123456'}).catch(e => e)
  expect(error).toBeInstanceOf(ApiError)
  if (!(error instanceof ApiError)) throw new Error('Expected ApiError')
  expect(error.message).not.toContain('PRIVATE')
})
