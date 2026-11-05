import { newRequestId, type LessonDetail, type Run } from './api'

export type OfflineBundle = {
  protocol: 1; server_id: string; content_hash: string; downloaded_at: string; lesson: LessonDetail
}
export type OfflineAttempt = {
  id: string; bundle: OfflineBundle; startedAt: string; completedAt: string | null
  answers: Record<number, string>; revision: number
  status: 'draft' | 'queued' | 'synced' | 'conflict'; error: string
  result?: Run; receivedAt?: string
}
const DATABASE = 'academy-offline-v1'
export const OFFLINE_CHANGED = 'academy-offline-change'

function changed() {
  window.dispatchEvent(new Event(OFFLINE_CHANGED))
  try { localStorage.setItem('academy-offline-pulse', newRequestId()) } catch { /* Same-tab events still work. */ }
}

async function openDatabase(): Promise<IDBDatabase> {
  if (!('indexedDB' in globalThis)) throw new Error('Браузер не предоставляет локальное хранилище. Открой Academy AI в обычном режиме браузера.')
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => {
      request.result.createObjectStore('lessons', { keyPath: 'slug' })
      request.result.createObjectStore('attempts', { keyPath: 'id' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error('Не удалось открыть локальную библиотеку. Проверь доступное место и разрешения браузера.'))
    request.onblocked = () => reject(new Error('Закрой другие вкладки Academy AI для обновления локального хранилища.'))
  })
}

async function transaction<T>(store: string, mode: IDBTransactionMode,
  operation: (objectStore: IDBObjectStore, finish: (value: T) => void, fail: (error: Error) => void) => void): Promise<T> {
  const db = await openDatabase()
  return new Promise((resolve, reject) => {
    let result: T
    let failure: Error | undefined
    const tx = db.transaction(store, mode)
    tx.oncomplete = () => { db.close(); if (mode === 'readwrite') changed(); resolve(result) }
    tx.onabort = () => { db.close(); reject(failure ?? new Error('Не удалось сохранить данные на устройстве. Освободи место и повтори сохранение.')) }
    tx.onerror = () => { /* onabort handles failures without reporting a premature save. */ }
    try {
      operation(tx.objectStore(store), value => { result = value }, error => { failure = error; tx.abort() })
    } catch (error) {
      failure = error instanceof Error ? error : new Error('Ошибка локального хранения')
      tx.abort()
    }
  })
}

export function listBundles(): Promise<OfflineBundle[]> {
  return transaction('lessons', 'readonly', (store, finish) => {
    store.getAll().onsuccess = event => finish((event.target as IDBRequest).result.map((row: { bundle: OfflineBundle }) => row.bundle))
  })
}

export function saveBundle(bundle: OfflineBundle): Promise<OfflineBundle> {
  return transaction('lessons', 'readwrite', (store, finish) => {
    store.put({ slug: bundle.lesson.slug, bundle }); finish(bundle)
  })
}

export function listAttempts(): Promise<OfflineAttempt[]> {
  return transaction('attempts', 'readonly', (store, finish) => {
    store.getAll().onsuccess = event => finish((event.target as IDBRequest).result)
  })
}

export function startOffline(bundle: OfflineBundle): Promise<OfflineAttempt> {
  if (bundle.lesson.unlocked === false) return Promise.reject(new Error('Практика этого урока ещё закрыта. После освоения предыдущих тем обнови сохранённый урок.'))
  return transaction('attempts', 'readwrite', (store, finish, fail) => {
    store.getAll().onsuccess = event => {
      const existing = (event.target as IDBRequest<OfflineAttempt[]>).result.find(a => a.bundle.lesson.slug === bundle.lesson.slug && a.status === 'draft')
      if (existing) { finish(existing); return }
      if (bundle.lesson.exercises.some(e => !['choice', 'text'].includes(e.kind))) {
        fail(new Error('Этот урок требует онлайн-практики.')); return
      }
      const attempt: OfflineAttempt = { id: newRequestId(), bundle, startedAt: new Date().toISOString(),
        completedAt: null, answers: {}, revision: 0, status: 'draft', error: '' }
      store.add(attempt); finish(attempt)
    }
  })
}

function editAttempt(id: string, edit: (attempt: OfflineAttempt) => OfflineAttempt): Promise<OfflineAttempt> {
  return transaction('attempts', 'readwrite', (store, finish, fail) => {
    store.get(id).onsuccess = event => {
      const current: OfflineAttempt | undefined = (event.target as IDBRequest).result
      if (!current) { fail(new Error('Локальная попытка не найдена')); return }
      try { const result = edit(current); store.put(result); finish(result) }
      catch (error) { fail(error instanceof Error ? error : new Error('Не удалось обновить попытку')) }
    }
  })
}

export function saveDraft(id: string, revision: number, answers: Record<number, string>): Promise<OfflineAttempt> {
  return editAttempt(id, attempt => {
    if (attempt.status !== 'draft' || attempt.revision !== revision) throw new Error('Попытка изменена в другой вкладке. Скопируй свой текст и открой сохранённую версию заново.')
    return { ...attempt, answers, revision: revision + 1 }
  })
}

export function queueAttempt(id: string, revision: number): Promise<OfflineAttempt> {
  return editAttempt(id, attempt => {
    if (attempt.status !== 'draft' || attempt.revision !== revision) throw new Error('Попытка изменилась. Открой её заново перед отправкой.')
    if (attempt.bundle.lesson.exercises.some(e => !attempt.answers[e.id]?.trim())) throw new Error('Ответь на все упражнения перед отправкой.')
    return { ...attempt, status: 'queued', completedAt: new Date().toISOString(), revision: revision + 1 }
  })
}

export function acknowledge(id: string, result: Run, receivedAt: string): Promise<OfflineAttempt> {
  return editAttempt(id, attempt => {
    if (!['queued', 'synced'].includes(attempt.status) || result.id !== id) throw new Error('Сервер вернул неожиданный идентификатор попытки')
    return { ...attempt, status: 'synced', result, receivedAt, error: '' }
  })
}

export function flagConflict(id: string, error: string): Promise<OfflineAttempt> {
  return editAttempt(id, attempt => attempt.status === 'queued' ? { ...attempt, status: 'conflict', error } : attempt)
}

export function retryAttempt(id: string): Promise<OfflineAttempt> {
  return editAttempt(id, attempt => attempt.status === 'conflict' ? { ...attempt, status: 'queued', error: '' } : attempt)
}

export function submission(attempt: OfflineAttempt) {
  return { protocol: 1, attempt_id: attempt.id, server_id: attempt.bundle.server_id,
    lesson_slug: attempt.bundle.lesson.slug, content_version: attempt.bundle.lesson.version,
    content_hash: attempt.bundle.content_hash, started_at: attempt.startedAt, completed_at: attempt.completedAt,
    answers: Object.entries(attempt.answers).map(([exercise_id, answer]) => ({ exercise_id: Number(exercise_id), answer })) }
}
