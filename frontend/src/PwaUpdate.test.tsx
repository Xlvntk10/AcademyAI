import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { UpdateNotice } from './PwaUpdate'

const worker = vi.hoisted(() => ({postMessage:vi.fn()}))
vi.mock('./pwa', () => ({waitingWorker:()=>worker,checkPwaUpdate:vi.fn(async()=>{})}))
afterEach(() => { cleanup(); vi.clearAllMocks() })

test('an available update waits for user action and does not interrupt a lesson', async () => {
  const first = render(<UpdateNotice route="lesson/a2-daily-routine"/>)
  expect(screen.getByText('Готова новая версия Academy AI')).toBeVisible()
  expect(screen.queryByRole('button',{name:'Обновить приложение'})).not.toBeInTheDocument()
  expect(worker.postMessage).not.toHaveBeenCalled()
  await userEvent.setup().click(screen.getByRole('link',{name:'Перейти к обновлению'}))
  expect(worker.postMessage).not.toHaveBeenCalled()
  first.unmount()
  render(<UpdateNotice route="settings"/>)
  expect(screen.getByRole('button',{name:'Обновить приложение'})).toBeEnabled()
  expect(worker.postMessage).not.toHaveBeenCalled()
})
