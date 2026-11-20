import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { AccountGate, remember } from './Account'
import { setAccountContext } from './account-context'

vi.mock('./Settings', () => ({ default: () => null, ReminderHost: () => null }))
vi.mock('./Offline', () => ({ default: () => null, DownloadLesson: () => null,
  SyncStatus: () => null, OfflineLanding: () => <p>Saved offline library</p> }))
vi.mock('./PwaUpdate', () => ({ UpdateNotice: () => null }))
vi.mock('./Analytics', () => ({ default: () => <p>Progress loaded</p>, Motivation: () => null }))

const owner = { id: '11111111-1111-4111-8111-111111111111', email: '', namespace: 'acct-project-one' }

beforeEach(() => {
  localStorage.clear()
  setAccountContext(null)
  remember({ mode: 'supabase', user: owner })
  window.history.replaceState(null, '', '/#progress')
})
afterEach(() => {
  cleanup()
  setAccountContext(null)
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

test('retry on the offline progress screen revalidates the session before loading private data', async () => {
  const requests: string[] = []
  const fetch = vi.fn(async (url: string) => {
    requests.push(url)
    if (requests.length === 1) throw new TypeError('network unavailable')
    const result = url.endsWith('/session') ? { mode: 'supabase', user: owner }
      : url.endsWith('/lessons') ? []
      : { total_xp: 40, completed_lessons: 1, completed_runs: 1, lessons: [] }
    return { ok: true, json: async () => result }
  })
  vi.stubGlobal('fetch', fetch)
  render(<AccountGate><App /></AccountGate>)
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Повторить' }))
  expect(await screen.findByText('40 XP')).toBeVisible()
  expect(requests.slice(0, 2)).toEqual(['/api/auth/session', '/api/auth/session'])
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('retry cannot fetch another account progress when the server session has changed', async () => {
  const requests: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    requests.push(url)
    if (requests.length === 1) throw new TypeError('network unavailable')
    return { ok: true, json: async () => ({ mode: 'supabase', user: { ...owner, id: 'other', namespace: 'acct-project-two' } }) }
  }))
  render(<AccountGate><App /></AccountGate>)
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Повторить' }))
  expect(await screen.findByRole('heading', { name: 'Аккаунт изменился' })).toBeVisible()
  expect(requests).toEqual(['/api/auth/session', '/api/auth/session'])
})
