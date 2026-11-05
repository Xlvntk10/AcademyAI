import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { saveBundle, listBundles, startOffline, saveDraft, queueAttempt, listAttempts, submission, retryAttempt, type OfflineBundle } from './offline-store'
import { synchronize, syncStatus } from './offline-sync'
import OfflineLibrary from './Offline'
import App, { readRoute } from './App'

const bundle: OfflineBundle = {
  protocol: 1, server_id:'22222222-2222-4222-8222-222222222222', content_hash:'a'.repeat(64), downloaded_at:'2026-11-05T10:00:00Z',
  lesson: { id:1,slug:'sample',title:'A saved lesson',summary:'Theory',level:'A2',duration_minutes:10,
    exercise_count:1,max_score:10,version:1,subject:'english',topic:'Grammar',position:1,unlocked:true,
    theory:[{title:'A useful rule',body:'The explanation.',examples:['An example.']}],
    exercises:[{id:1,question:'Complete the sentence',points:10,position:1,kind:'text',options:[]}] }
}
beforeEach(() => { vi.stubGlobal('indexedDB', new IDBFactory()); vi.stubGlobal('scrollTo', vi.fn()); localStorage.clear() })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); window.history.replaceState(null,'','/') })

async function queuedAttempt() {
  const attempt = await startOffline(bundle)
  const saved = await saveDraft(attempt.id, 0, {1:'answer'})
  return queueAttempt(attempt.id, saved.revision)
}

test('IndexedDB persists bundles and drafts, keeps immutable version snapshots, and rejects stale tabs', async () => {
  await saveBundle(bundle)
  expect(await listBundles()).toEqual([bundle])
  const attempt = await startOffline(bundle)
  expect((await startOffline(bundle)).id).toBe(attempt.id)
  const saved = await saveDraft(attempt.id, 0, {1:'my first answer'})
  await expect(saveDraft(attempt.id, 0, {1:'stale tab'})).rejects.toThrow('другой вкладке')
  expect((await listAttempts())[0].answers).toEqual({1:'my first answer'})
  await saveBundle({...bundle,lesson:{...bundle.lesson,version:2}})
  expect((await listAttempts())[0].bundle.lesson.version).toBe(1)
  const queued = await queueAttempt(attempt.id, saved.revision)
  await expect(saveDraft(attempt.id, queued.revision, {1:'late edit'})).rejects.toThrow()
  expect(submission(queued).content_version).toBe(1)
  expect(submission(queued)).not.toHaveProperty('score')
})

test('lost network response retains queue and retries the exact same UUID and answers', async () => {
  const attempt = await queuedAttempt()
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('offline'))
  vi.stubGlobal('fetch', fetch)
  await synchronize()
  expect(syncStatus().state).toBe('unavailable')
  expect((await listAttempts())[0].status).toBe('queued')
  const result = {id:attempt.id,score:10,max_score:10,answers:[]}
  fetch.mockResolvedValue({ok:true,json:async()=>({attempt_id:attempt.id,received_at:'2026-11-05T12:00:00Z',result})})
  await Promise.all([synchronize(), synchronize()])
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body)
  expect((await listAttempts())[0].status).toBe('synced')
  await synchronize()
  expect(fetch).toHaveBeenCalledTimes(2)
})

test('version conflicts retain answers and require explicit retry', async () => {
  const attempt = await queuedAttempt()
  const fetch = vi.fn(async () => ({ok:false,status:409,json:async()=>({detail:'Урок обновлён'})}))
  vi.stubGlobal('fetch', fetch)
  await synchronize()
  expect((await listAttempts())[0]).toMatchObject({status:'conflict',answers:{1:'answer'},error:'Урок обновлён'})
  await synchronize()
  expect(fetch).toHaveBeenCalledTimes(1)
  await retryAttempt(attempt.id)
  await synchronize()
  expect(fetch).toHaveBeenCalledTimes(2)
})

test('storage abort never reports a draft as saved and the previous answer remains durable', async () => {
  const attempt = await startOffline(bundle)
  const saved = await saveDraft(attempt.id, 0, {1:'durable'})
  // Use the implementation's own store prototype through a temporary database.
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('academy-offline-v1',1)
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error)
  })
  const prototype = Object.getPrototypeOf(db.transaction('attempts').objectStore('attempts'))
  const put = vi.spyOn(prototype,'put').mockImplementation(() => { throw new DOMException('Quota exceeded','QuotaExceededError') })
  await expect(saveDraft(attempt.id, saved.revision, {1:'lost write'})).rejects.toThrow()
  put.mockRestore(); db.close()
  expect((await listAttempts())[0].answers).toEqual({1:'durable'})
})

test('offline UI restores typed answers after remount and queues without displaying invented scores', async () => {
  await saveBundle(bundle)
  vi.stubGlobal('fetch',vi.fn(async () => { throw new TypeError('offline') }))
  const user = userEvent.setup()
  const first = render(<OfflineLibrary lessons={[]}/>)
  await user.click(await screen.findByRole('button',{name:/A saved lesson/}))
  expect(screen.getByText('The explanation.')).toBeVisible()
  await user.click(screen.getByRole('button',{name:'Практика на устройстве'}))
  await user.type(await screen.findByRole('textbox'), 'answer')
  await waitFor(() => expect(screen.getByText('Черновик сохранён на устройстве')).toBeVisible())
  first.unmount()
  render(<OfflineLibrary lessons={[]}/>)
  await user.click(await screen.findByRole('button',{name:'Продолжить черновик'}))
  expect(await screen.findByRole('textbox')).toHaveValue('answer')
  await user.click(screen.getByRole('button',{name:'Завершить и поставить в очередь'}))
  expect(await screen.findByText('Ответы в очереди')).toBeVisible()
  await synchronize()
  expect((await listAttempts())[0]).toMatchObject({status:'queued',answers:{1:'answer'}})
  expect(screen.queryByText(/10 баллов/)).not.toBeInTheDocument()
})

test('the normal app entry opens the offline library when every API call fails', async () => {
  await saveBundle(bundle)
  window.location.hash = '#offline'
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('server stopped') }))
  render(<App />)
  expect(await screen.findByRole('button',{name:/A saved lesson/})).toBeVisible()
  expect(screen.getByRole('heading',{name:'Уроки с собой'})).toBeVisible()
  expect(screen.getByText(/—\s*XP/)).toBeVisible()
})

test.each(['today','learn','plan','progress'])('cold /%s renders an explicit empty offline screen', async route => {
  window.history.replaceState(null,'',`/${route}`)
  expect(readRoute()).toBe(route)
  vi.stubGlobal('fetch',vi.fn(async()=>{throw new TypeError('servers stopped')}))
  render(<App/>)
  expect(await screen.findByRole('heading',{name:'Учёба без подключения'})).toBeVisible()
  expect(await screen.findByText(/Скачанных уроков пока нет/)).toBeVisible()
  expect(screen.getByRole('link',{name:'Локальная библиотека и мои ответы'})).toHaveAttribute('href','#offline')
})

test('cold path routes surface IndexedDB lessons and preserve legacy hash navigation', async () => {
  await saveBundle(bundle)
  window.history.replaceState(null,'','/learn')
  vi.stubGlobal('fetch',vi.fn(async()=>{throw new TypeError('servers stopped')}))
  render(<App/>)
  await userEvent.setup().click(await screen.findByRole('link',{name:/A saved lesson/}))
  expect(readRoute()).toBe('offline')
  expect(await screen.findByRole('button',{name:/A saved lesson/})).toBeVisible()
})
