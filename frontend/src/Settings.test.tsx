import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, test, expect, vi } from 'vitest'
import Settings, { ReminderHost } from './Settings'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); localStorage.removeItem('academy-reminder-day') })
test('saving reminder uses narrow fields and never requests notification permission automatically', async () => {
  const requestPermission = vi.fn()
  vi.stubGlobal('Notification', { permission:'default', requestPermission })
  vi.stubGlobal('isSecureContext',true)
  const settings = { available_minutes:[90,90,90,90,90,180,180],daily_goal_minutes:30,weekly_goal_minutes:210,reminder_enabled:false,reminder_time:'19:00',timezone:'Asia/Almaty',english_percent:65 }
  const fetch = vi.fn(async (_url: string, options?: RequestInit) => { if (options?.body) Object.assign(settings,JSON.parse(options.body as string)); return {ok:true,json:async()=>settings} })
  vi.stubGlobal('fetch',fetch)
  render(<Settings />)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('checkbox',{name:'Напоминать при открытом приложении'}))
  await user.click(screen.getByRole('button',{name:'Сохранить'}))
  expect(await screen.findByText('Время занятий сохранено.')).toBeVisible()
  const call = fetch.mock.calls.find(args => args[0] === '/api/planner/reminder')!
  expect(JSON.parse(call[1]!.body as string)).toEqual({reminder_enabled:true,reminder_time:'19:00'})
  expect(requestPermission).not.toHaveBeenCalled()
})

test('reminder uses Almaty time, waits for a visible page and fires once per local day across remounts', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-04T13:59:30Z'))
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const notification = vi.fn(function () {})
  Object.assign(notification, { permission: 'granted' })
  vi.stubGlobal('Notification', notification)
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ reminder_enabled: true, reminder_time: '19:00' }) })))
  const first = render(<ReminderHost />)
  await act(async () => {})
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(notification).not.toHaveBeenCalled()
  visibility.mockReturnValue('visible')
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(notification).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('status')).toHaveTextContent('Время для небольшого шага')
  expect(localStorage.getItem('academy-reminder-day')).toBe('2026-11-04')
  first.unmount()
  render(<ReminderHost />)
  await act(async () => {})
  expect(notification).toHaveBeenCalledTimes(1)
  vi.setSystemTime(new Date('2026-11-05T14:00:00Z'))
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(notification).toHaveBeenCalledTimes(2)
})
