export type Exercise = { id: number; question: string; points: number; position: number; kind: 'choice' | 'text'; options: string[] }
export type Theory = { title: string; body: string; examples: string[] }
export type Lesson = { id: number; slug: string; title: string; summary: string; level: string; duration_minutes: number; exercise_count: number; max_score: number; version: number }
export type LessonDetail = Lesson & { theory: Theory[]; exercises: Exercise[] }
export type Answer = { exercise_id: number; answer: string; is_correct: boolean; earned_points: number; correct_answer: string; explanation: string }
export type Run = { id: string; lesson_slug: string; started_at: string; completed_at: string | null; answered_count: number; exercise_count: number; correct_count: number; score: number; max_score: number; answers: Answer[] }
export type Stats = { slug: string; completed_runs: number; best_score: number; max_score: number; active_run_id: string | null; last_result: Run | null }
export type Progress = { completed_lessons: number; completed_runs: number; total_xp: number; lessons: Stats[] }

export async function api<T>(path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    })
  } catch {
    throw new Error('Нет связи с Academy AI. Проверь подключение и попробуй ещё раз. Уже сохранённые ответы останутся в базе.')
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : 'Не удалось выполнить запрос. Попробуй ещё раз.')
  }
  return response.json()
}

// getRandomValues works on a phone over a trusted local HTTP network too.
export function newRequestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
