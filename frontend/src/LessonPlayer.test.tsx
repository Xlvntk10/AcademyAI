import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { LessonPlayer } from './App'
import type { LessonDetail, Run } from './api'

const lesson: LessonDetail = {
  id: 5, slug: 'a2-daily-routine', title: 'A little every day', level: 'A2', summary: 'Present Simple',
  duration_minutes: 12, version: 1, exercise_count: 1, max_score: 10,
  theory: [{ title: 'Теория', body: 'После she добавляем -s.', examples: ['She studies.'] }],
  exercises: [{ id: 6, question: 'She ___ English.', points: 10, kind: 'choice', position: 1, options: ['study', 'studies'] }],
}
const initial: Run = { id: '123e4567-e89b-42d3-a456-426614174000', lesson_slug: lesson.slug, started_at: '2026-11-04T10:00:00Z', completed_at: null, answered_count: 0, exercise_count: 1, score: 0, max_score: 10, correct_count: 0, answers: [] }

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test('submits only the answer, shows server feedback and restores result after remount', async () => {
  let saved: Run | null = null
  const requests: unknown[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    let data: unknown
    if (url.endsWith('/progress')) data = { completed_lessons: saved?.completed_at ? 1 : 0, completed_runs: saved?.completed_at ? 1 : 0, total_xp: saved?.score ?? 0, lessons: [{ slug: lesson.slug, active_run_id: saved && !saved.completed_at ? saved.id : null, last_result: saved?.completed_at ? saved : null }] }
    else if (url.endsWith('/answers')) {
      requests.push(JSON.parse(options!.body as string))
      saved = { ...initial, completed_at: '2026-11-04T10:02:00Z', score: 10, correct_count: 1, answered_count: 1, answers: [{ exercise_id: 6, answer: 'studies', is_correct: true, earned_points: 10, correct_answer: 'studies', explanation: 'После she нужна форма studies.' }] }
      data = saved
    } else if (url.endsWith('/runs')) { saved = { ...initial }; data = saved }
    else if (url.includes('/runs/')) data = saved
    else data = lesson
    return { ok: true, json: async () => data }
  }))
  const user = userEvent.setup()
  const props = { slug: lesson.slug, onSaved: vi.fn(), onExit: vi.fn() }
  const view = render(<LessonPlayer {...props} />)
  await user.click(await screen.findByRole('button', { name: /Начать практику/ }))
  expect(await screen.findByRole('button', { name: /Проверить ответ/ })).toBeDisabled()
  await user.click(screen.getByRole('radio', { name: /studies/ }))
  await user.click(screen.getByRole('button', { name: /Проверить ответ/ }))
  expect(await screen.findByText('Верно! +10 баллов')).toBeVisible()
  expect(requests).toEqual([{ exercise_id: 6, answer: 'studies' }])
  await user.click(screen.getByRole('button', { name: /Посмотреть результат/ }))
  expect(await screen.findByRole('heading', { name: 'Урок завершён!' })).toBeVisible()
  view.unmount()
  render(<LessonPlayer {...props} />)
  expect(await screen.findByRole('heading', { name: 'Урок завершён!' })).toBeVisible()
  expect(screen.getByText(/Результат сохранён/)).toBeVisible()
})

test('a failed submission leaves the selected answer and allows a safe retry', async () => {
  let attempts = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/answers')) { attempts++; throw new TypeError('offline') }
    const data = url.endsWith('/progress') ? { lessons: [] } : url.endsWith('/runs') ? initial : lesson
    return { ok: true, json: async () => data }
  }))
  const user = userEvent.setup()
  render(<LessonPlayer slug={lesson.slug} onSaved={vi.fn()} onExit={vi.fn()} />)
  await user.click(await screen.findByRole('button', { name: /Начать практику/ }))
  await user.click(await screen.findByRole('radio', { name: /studies/ }))
  await user.click(screen.getByRole('button', { name: /Проверить ответ/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Нет связи')
  expect(screen.getByRole('radio', { name: /studies/ })).toBeChecked()
  await waitFor(() => expect(screen.getByRole('button', { name: /Проверить ответ/ })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: /Проверить ответ/ }))
  expect(attempts).toBe(2)
})

test('an unfinished lesson is resumed from the server', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/progress') ? { lessons: [{ slug: lesson.slug, active_run_id: initial.id, last_result: null }] } : url.includes('/runs/') ? initial : lesson })))
  render(<LessonPlayer slug={lesson.slug} onSaved={vi.fn()} onExit={vi.fn()} />)
  expect(await screen.findByRole('heading', { name: 'She ___ English.' })).toBeVisible()
  expect(screen.queryByRole('button', { name: /Начать практику/ })).not.toBeInTheDocument()
})
