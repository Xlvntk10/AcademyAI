import { api, ApiError, type Run } from './api'
import { acknowledge, flagConflict, listAttempts, submission } from './offline-store'

export type SyncState = 'idle' | 'syncing' | 'unavailable' | 'error'
let current: Promise<void> | null = null
let state: SyncState = 'idle'
let detail = ''
export const syncStatus = () => ({ state, detail })
function announce(next: SyncState, message = '') {
  state = next; detail = message
  window.dispatchEvent(new Event('academy-sync-state'))
}

async function sendQueue() {
  try {
    const queued = (await listAttempts()).filter(a => a.status === 'queued').sort((a, b) => a.startedAt.localeCompare(b.startedAt))
    if (!queued.length) { announce('idle'); return }
    announce('syncing')
    for (const attempt of queued) {
      let receipt: { attempt_id: string; received_at: string; result: Run }
      try {
        receipt = await api('/offline/attempts', submission(attempt))
      } catch (error) {
        if (error instanceof ApiError && [400, 404, 409, 422].includes(error.status)) {
          await flagConflict(attempt.id, error.message)
          continue
        }
        announce('unavailable', error instanceof Error ? error.message : 'Сервер недоступен')
        return
      }
      if (receipt.attempt_id !== attempt.id) throw new Error('Сервер вернул чужую попытку. Локальные ответы сохранены.')
      await acknowledge(attempt.id, receipt.result, receipt.received_at)
      window.dispatchEvent(new Event('academy-sync-complete'))
    }
    announce('idle')
  } catch (error) {
    announce('error', error instanceof Error ? error.message : 'Ошибка локального хранения')
  }
}

export function synchronize(): Promise<void> {
  if (current) return current
  // Web Locks prevent duplicate sends across tabs. The server also guarantees idempotency.
  current = (async () => {
    if (navigator.locks) await navigator.locks.request('academy-sync-v1', sendQueue)
    else await sendQueue()
  })().finally(() => { current = null })
  return current
}
