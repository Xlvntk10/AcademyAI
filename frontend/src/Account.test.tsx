import { IDBFactory } from 'fake-indexeddb'
import { cleanup, render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AccountGate } from './Account'
import { accountNamespace, privateKey, setAccountContext, type AccountUser } from './account-context'
import { api } from './api'
import { listAttempts, listBundles, saveBundle, startOffline, saveDraft, queueAttempt, type OfflineBundle } from './offline-store'
import { synchronize } from './offline-sync'

const alice: AccountUser = {id:'11111111-1111-4111-8111-111111111111', email:'one@example.test', namespace:'acct-project-one'}
const bob: AccountUser = {id:'22222222-2222-4222-8222-222222222222', email:'two@example.test', namespace:'acct-project-two'}
const bundle: OfflineBundle = {
  protocol:1, server_id:'33333333-3333-4333-8333-333333333333', content_hash:'a'.repeat(64), downloaded_at:'2026-11-05T10:00:00Z',
  lesson:{id:1,slug:'sample',title:'Saved lesson',summary:'Theory',level:'A2',duration_minutes:10,exercise_count:1,max_score:10,
    version:1,subject:'english',topic:'Grammar',position:1,unlocked:true,theory:[],exercises:[{id:1,question:'Answer',points:10,position:1,kind:'text',options:[]}]},
}
beforeEach(() => { localStorage.clear(); setAccountContext(null); vi.stubGlobal('indexedDB', new IDBFactory()) })
afterEach(() => { cleanup(); setAccountContext(null); vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); localStorage.clear() })

test('account namespaces preserve legacy storage and isolate lessons, drafts and queues', async () => {
  await saveBundle(bundle)
  setAccountContext(alice)
  expect(await listBundles()).toEqual([])
  await saveBundle(bundle)
  const draft = await startOffline(bundle)
  const saved = await saveDraft(draft.id, 0, {1:'answer'})
  await queueAttempt(draft.id, saved.revision)
  expect(privateKey('academy-local-recordings')).toContain(alice.namespace)
  setAccountContext(bob)
  expect(await listAttempts()).toEqual([])
  expect(await listBundles()).toEqual([])
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  await synchronize()
  expect(fetch).not.toHaveBeenCalled()
  setAccountContext(alice)
  expect((await listAttempts())[0]).toMatchObject({id:draft.id, status:'queued', answers:{1:'answer'}})
  setAccountContext(null)
  expect(await listBundles()).toHaveLength(1)
})

test('API binds requests to the account and sends the viewed planner revision', async () => {
  setAccountContext(alice)
  const fetch = vi.fn(async () => ({ok:true,json:async()=>({saved:true})}))
  vi.stubGlobal('fetch',fetch)
  await api('/planner/settings', {sync_revision:'viewed-version',english_percent:70})
  expect(fetch.mock.calls[0]).toEqual(['/api/planner/settings',expect.objectContaining({
    credentials:'same-origin',cache:'no-store',
    headers:expect.objectContaining({'X-Academy-Account':alice.id,'X-Academy-Request':'1','If-Match':'viewed-version'}),
    body:'{"english_percent":70}',
  })])
  setAccountContext(alice,false)
  await expect(api('/offline/attempts',{})).rejects.toThrow('Офлайн')
  expect(fetch).toHaveBeenCalledTimes(1)
})

test('cold offline account startup restores only its local namespace without sending answers', async () => {
  localStorage.setItem('academy-account-v4',JSON.stringify({mode:'supabase',user:alice}))
  const fetch = vi.fn(async()=>{throw new TypeError('offline')})
  vi.stubGlobal('fetch',fetch)
  render(<AccountGate><h1>Private library</h1></AccountGate>)
  expect(await screen.findByRole('heading',{name:'Private library'})).toBeVisible()
  expect(accountNamespace()).toBe(alice.namespace)
  await expect(api('/progress')).rejects.toThrow('Офлайн')
  expect(fetch).toHaveBeenCalledTimes(1)
})

test('signed-out account shows login and submits registration through the provider boundary', async () => {
  const fetch = vi.fn(async (url:string) => ({ok:true,json:async()=>url.endsWith('/session') ? {mode:'supabase',user:null} : {message:'Код отправлен'}}))
  vi.stubGlobal('fetch',fetch)
  const user = userEvent.setup()
  render(<AccountGate><h1>Private library</h1></AccountGate>)
  expect(await screen.findByText('Made by Kusymbaev Alan')).toBeVisible()
  await user.click(await screen.findByRole('button',{name:'Зарегистрироваться'}))
  expect(screen.getByText('Made by Kusymbaev Alan')).toBeVisible()
  expect(screen.getByRole('button',{name:'Проверить обновления'})).toBeVisible()
  await user.type(screen.getByLabelText('Email'),'one@example.test')
  await user.selectOptions(screen.getByLabelText('Способ входа'), 'code')
  await user.click(screen.getByRole('button',{name:'Получить код'}))
  expect(await screen.findByLabelText('Код из письма')).toBeVisible()
  expect(fetch.mock.calls[1]).toEqual(['/api/auth/code',expect.objectContaining({body:'{"email":"one@example.test","register":true}'})])
  expect(screen.queryByRole('heading',{name:'Private library'})).not.toBeInTheDocument()
})

test('a cross-tab account switch hides the old interface and blocks its network requests', async () => {
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({mode:'supabase',user:alice})})))
  render(<AccountGate><h1>Private library</h1></AccountGate>)
  await screen.findByRole('heading',{name:'Private library'})
  act(()=>window.dispatchEvent(new StorageEvent('storage',{key:'academy-account-v4'})))
  await waitFor(()=>expect(screen.queryByRole('heading',{name:'Private library'})).not.toBeInTheDocument())
  expect(screen.getByRole('heading',{name:'Аккаунт изменился'})).toBeVisible()
  await expect(api('/progress')).rejects.toThrow('Офлайн')
})

test('a fresh cloud install shows reconnect instead of entering a local profile during an outage', async () => {
  vi.stubEnv('VITE_ACCOUNT_MODE', 'supabase')
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValue({ok:true,json:async()=>({mode:'supabase',user:alice})})
  vi.stubGlobal('fetch',fetch)
  const user = userEvent.setup()
  render(<AccountGate><h1>Private library</h1></AccountGate>)
  await user.click(await screen.findByRole('button',{name:'Повторить подключение'}))
  expect(await screen.findByRole('heading',{name:'Private library'})).toBeVisible()
  expect(accountNamespace()).toBe(alice.namespace)
  expect(fetch).toHaveBeenCalledTimes(2)
})

test('expired sessions require login and keep queued answers in the original account', async () => {
  setAccountContext(alice)
  await saveBundle(bundle)
  const draft = await startOffline(bundle)
  const saved = await saveDraft(draft.id,0,{1:'offline answer'})
  await queueAttempt(draft.id,saved.revision)
  localStorage.setItem('academy-account-v4',JSON.stringify({mode:'supabase',user:alice}))
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:401,json:async()=>({detail:'expired'})})))
  render(<AccountGate><h1>Private library</h1></AccountGate>)
  expect(await screen.findByRole('heading',{name:'Войти в своё обучение'})).toBeVisible()
  expect(screen.queryByRole('heading',{name:'Private library'})).not.toBeInTheDocument()
  expect(await listAttempts()).toEqual([expect.objectContaining({id:draft.id,status:'queued',answers:{1:'offline answer'}})])
  await expect(api('/offline/attempts',{})).rejects.toThrow('Офлайн')
})
