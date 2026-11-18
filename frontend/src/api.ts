export type Exercise = { id: number; question: string; points: number; position: number; kind: 'choice' | 'text'; options: string[] }
export type Theory = { title: string; body: string; examples: string[]; code?: string | null }
export type Lesson = { id: number; slug: string; title: string; summary: string; level: string; duration_minutes: number; exercise_count: number; max_score: number; version: number; subject: 'english' | 'python'; topic: string; position: number; unlocked?: boolean; mastered?: boolean; prerequisites?: string[]; best_percent?: number }
export type LessonDetail = Lesson & { theory: Theory[]; exercises: Exercise[] }
export type Answer = { exercise_id: number; answer: string; is_correct: boolean; earned_points: number; correct_answer: string; explanation: string }
export type Run = { id: string; lesson_slug: string; started_at: string; completed_at: string | null; answered_count: number; exercise_count: number; correct_count: number; score: number; max_score: number; answers: Answer[] }
export type Stats = { slug: string; completed_runs: number; best_score: number; max_score: number; active_run_id: string | null; last_result: Run | null }
export type Progress = { completed_lessons: number; completed_runs: number; total_xp: number; lessons: Stats[] }

import { accountUser, canConnect } from './account-context'

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const authRequest = path.startsWith('/auth/')
  if (!authRequest && !canConnect()) throw new Error('Офлайн-режим. Подключись и подтверди аккаунт перед отправкой ответов.')
  const headers: Record<string, string> = { 'X-Academy-Request': '1' }
  const owner = accountUser()?.id
  if (owner) headers['X-Academy-Account'] = owner
  let payload = body
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    if (body && typeof body === 'object' && 'sync_revision' in body) {
      const { sync_revision, ...fields } = body
      if (typeof sync_revision === 'string') headers['If-Match'] = sync_revision
      payload = fields
    }
  }
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(payload),
      signal: AbortSignal.timeout(15000),
      cache: 'no-store',
    })
  } catch {
    throw new Error('Нет связи с Academy AI. Сервер может запускаться. Повтори подключение через минуту. Локальные ответы сохранены.')
  }
  if (!response.ok) {
    if (response.status === 401 && !authRequest) window.dispatchEvent(new Event('academy-session-expired'))
    const error = await response.json().catch(() => null)
    throw new ApiError(typeof error?.detail === 'string' ? error.detail : 'Не удалось выполнить запрос. Проверь ответы и настройки времени устройства.', response.status)
  }
  // A sleeping host or a misconfigured static rewrite can return HTML with 200.
  // Preserve drafts and show a useful connection error instead of a JSON exception.
  try {
    return await response.json()
  } catch {
    throw new ApiError('Сервер ещё запускается или вернул неверный ответ. Повтори подключение через минуту. Локальные ответы сохранены.', 503)
  }
}

// getRandomValues works on a phone over a trusted local HTTP network too.
export function newRequestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
