import { StrictMode } from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { MagicLinkCallback, readLinkCallback } from './MagicLink'
import { AccountGate } from './Account'
import { setAccountContext } from './account-context'

afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear()
  window.history.replaceState(null, '', '/'); setAccountContext(null)
})

test('callback code is captured once in memory and removed from the URL without storing it', () => {
  window.history.replaceState(null, '', '/auth/callback?code=one-time-code&next=https://evil.test')
  expect(readLinkCallback()).toEqual({code:'one-time-code'})
  expect(window.location.pathname).toBe('/auth/callback')
  expect(window.location.search).toBe('')
  expect(window.location.hash).toBe('')
  expect(localStorage.length).toBe(0)
  expect(sessionStorage.length).toBe(0)
  expect(readLinkCallback()?.error).toBeTruthy()
})

test.each([
  '/auth/callback?error=denied&error_description=SECRET',
  '/#access_token=SECRET&refresh_token=PRIVATE',
  '/auth/callback?code=one&code=two',
  '/auth/callback?code=%3Cscript%3E',
])('rejects unsafe or obsolete link without reflecting sensitive parameters: %s', path => {
  window.history.replaceState(null, '', path)
  const result = readLinkCallback()
  expect(result?.code).toBeUndefined()
  expect(result?.error).toBeTruthy()
  expect(JSON.stringify(result)).not.toContain('SECRET')
  expect(window.location.search + window.location.hash).toBe('')
})

test('ordinary learning navigation is not treated as an auth callback', () => {
  window.history.replaceState(null, '', '/learn#lesson/a2-daily-routine')
  expect(readLinkCallback()).toBeNull()
  expect(window.location.hash).toBe('#lesson/a2-daily-routine')
})

test('StrictMode exchanges only once and keeps only the offline namespace hint before profile navigation', async () => {
  const user = {id:'11111111-1111-4111-8111-111111111111', email:'one@example.test', namespace:'acct-realm-one'}
  const fetch = vi.fn(async () => new Response(JSON.stringify({mode:'supabase', user})))
  vi.stubGlobal('fetch', fetch)
  const onSuccess = vi.fn()
  render(<StrictMode><MagicLinkCallback callback={{code:'one-time-code'}} onSuccess={onSuccess}/></StrictMode>)
  await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce())
  expect(fetch).toHaveBeenCalledOnce()
  expect(fetch).toHaveBeenCalledWith('/api/auth/exchange', expect.objectContaining({method:'POST', credentials:'same-origin', cache:'no-store', body:'{"code":"one-time-code"}'}))
  const saved = localStorage.getItem('academy-account-v4')!
  expect(saved).toContain(user.namespace)
  expect(saved).not.toContain(user.email)
  expect(saved).not.toContain('one-time-code')
})

test('offline callback shows a retry and preserves existing offline markers', async () => {
  localStorage.setItem('academy-account-v4', 'previous-profile')
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(new Response(JSON.stringify({mode:'supabase',user:{id:'one', namespace:'acct-realm-one',email:'one@example.test'}})))
  vi.stubGlobal('fetch', fetch)
  const onSuccess = vi.fn()
  render(<MagicLinkCallback callback={{code:'one-time-code'}} onSuccess={onSuccess}/>)
  expect(await screen.findByRole('button', {name:'Повторить подключение'})).toBeVisible()
  expect(localStorage.getItem('academy-account-v4')).toBe('previous-profile')
  expect(onSuccess).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', {name:'Повторить подключение'}))
  await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce())
})

test('default login requests a magic link without asking for a numeric code', async () => {
  const fetch = vi.fn(async (path:string) => new Response(JSON.stringify(path.endsWith('/session') ? {mode:'supabase',user:null} : {message:'Проверь последнее письмо в этом браузере'})))
  vi.stubGlobal('fetch', fetch)
  render(<AccountGate><h1>Private content</h1></AccountGate>)
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Email'), 'one@example.test')
  await user.click(screen.getByRole('button', {name:'Получить ссылку'}))
  expect(await screen.findByText('Проверь последнее письмо в этом браузере')).toBeVisible()
  expect(screen.queryByLabelText('Код из письма')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenLastCalledWith('/api/auth/link', expect.objectContaining({body:'{"email":"one@example.test","register":false}'}))
})
