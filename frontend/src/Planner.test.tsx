import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import Planner, { type Week } from './Planner'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
test('generates a real week and shows server tasks on the selected day', async () => {
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Almaty', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  const week: Week = { week_start: date, today: date, generated: false, planned_minutes: 0, completed_minutes: 0, overdue: [], tasks: [], settings: { available_minutes: [90,90,90,90,90,180,180], daily_goal_minutes: 30, weekly_goal_minutes: 210, reminder_enabled: false, reminder_time: '19:00', timezone: 'Asia/Almaty', english_percent: 65 } }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/generate')) Object.assign(week, { generated: true, planned_minutes: 20, tasks: [{ id: 'task-1', scheduled_date: date, original_date: date, subject: 'english', kind: 'practice', title: 'Прочитай короткий текст', instructions: 'Выпиши пять слов.', planned_minutes: 20, status: 'pending', actual_minutes: null, completed_at: null, lesson_slug: null, overdue: false }] })
    return { ok: true, json: async () => ({ ...week }) }
  }))
  const user = userEvent.setup()
  render(<Planner onSaved={vi.fn()} />)
  await user.click(await screen.findByRole('button', { name: 'Составить неделю' }))
  expect(await screen.findByRole('heading', { name: 'Прочитай короткий текст' })).toBeVisible()
  expect(screen.getByText('Выпиши пять слов.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Расписание' }))
  expect(screen.getByLabelText('Пн')).toHaveValue(90)
})
