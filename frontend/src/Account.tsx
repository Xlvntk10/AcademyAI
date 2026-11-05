import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import { accountUser, setAccountContext, type AccountSession } from './account-context'
import { listAttempts, OFFLINE_CHANGED } from './offline-store'
import { synchronize } from './offline-sync'
import { message } from './Planner'

const markerKey = 'academy-account-v4'
const SessionContext = createContext({ session: {mode:'local', user:null} as AccountSession, offline:false })

function remember(session: AccountSession) {
  // Only an offline namespace hint. Authentication stays in the HttpOnly cookie.
  const hint = {...session, user: session.user ? {...session.user, email:''} : null}
  try { localStorage.setItem(markerKey, JSON.stringify(hint)) }
  catch { /* Cookie-authenticated online use remains available without localStorage. */ }
}

function remembered(): AccountSession {
  try {
    const value = JSON.parse(localStorage.getItem(markerKey) || 'null')
    if (value?.mode === 'supabase') {
      const user = value.user
      if (user && typeof user.id === 'string' && typeof user.namespace === 'string' && user.namespace.startsWith('acct-')) return value
      return {mode:'supabase', user:null}
    }
  } catch { /* Legacy local mode remains usable offline. */ }
  return {mode:'local', user:null}
}

function Login({notice}: {notice:string}) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [register, setRegister] = useState(false)
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(notice)
  async function submit() {
    setBusy(true)
    try {
      if (sent) {
        const session = await api<AccountSession>('/auth/verify', {email, code})
        remember(session)
        window.location.reload()
      } else {
        const result = await api<{message:string}>('/auth/code', {email, register})
        setStatus(result.message)
        setSent(true)
      }
    } catch (error) { setStatus(message(error)) }
    finally { setBusy(false) }
  }
  return <main className="account-entry"><section className="panel settings-panel">
    <h1>Academy AI</h1><h2>{register ? 'Создать аккаунт' : 'Войти в своё обучение'}</h2>
    <p>Вход по одноразовому коду из письма Supabase. Для восстановления доступа запроси новый код на прежний email.</p>
    <form onSubmit={event => { event.preventDefault(); void submit() }}>
      <label>Email<input type="email" required maxLength={254} autoComplete="email" value={email} disabled={sent || busy} onChange={event => setEmail(event.target.value)}/></label>
      {sent && <label>Код из письма<input required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6,10}" value={code} onChange={event => setCode(event.target.value)}/></label>}
      <button className="primary" disabled={busy}>{busy ? 'Подожди…' : sent ? 'Подтвердить вход' : 'Получить код'}</button>
    </form>
    {status && <p role="status">{status}</p>}
    <div className="button-row"><button className="text-button" disabled={busy} onClick={() => { setSent(false); setRegister(!register); setStatus('') }}>{register ? 'У меня уже есть аккаунт' : 'Зарегистрироваться'}</button>
      {sent && <button className="text-button" disabled={busy} onClick={() => { setSent(false); setCode('') }}>Другой адрес или новый код</button>}</div>
  </section></main>
}

export function AccountGate({children}: {children: ReactNode}) {
  const [session, setSession] = useState<AccountSession | null>(null)
  const [offline, setOffline] = useState(false)
  const [notice, setNotice] = useState('')
  const [blocked, setBlocked] = useState(false)
  const checking = useRef(false)
  const check = useCallback(async () => {
    if (checking.current) return
    checking.current = true
    try {
      const value = await api<AccountSession>('/auth/session')
      const current = accountUser()
      if (current && value.user?.namespace !== current.namespace) {
        setAccountContext(current, false)
        setBlocked(true)
        return
      }
      setAccountContext(value.user)
      remember(value)
      setSession(value)
      setOffline(false)
      setNotice('')
      window.dispatchEvent(new Event('academy-account-connected'))
    } catch (error) {
      const hint = remembered()
      setAccountContext(hint.user, false)
      setOffline(true)
      if (error instanceof ApiError && error.status === 401) {
        setSession({mode:'supabase', user:null})
        setNotice('Сессия закончилась. Войди снова, чтобы продолжить синхронизацию.')
      } else setSession(hint)
    } finally { checking.current = false }
  }, [])
  useEffect(() => {
    void check()
    const visible = () => { if (document.visibilityState === 'visible') void check() }
    const disconnected = () => { setAccountContext(accountUser(), false); setOffline(true) }
    const storage = (event: StorageEvent) => {
      if (event.key === markerKey) {
        setAccountContext(accountUser(), false)
        setBlocked(true)
      }
    }
    window.addEventListener('online', check)
    window.addEventListener('offline', disconnected)
    window.addEventListener('academy-session-expired', check)
    window.addEventListener('storage', storage)
    document.addEventListener('visibilitychange', visible)
    const timer = window.setInterval(visible, 60000)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('online', check)
      window.removeEventListener('offline', disconnected)
      window.removeEventListener('academy-session-expired', check)
      window.removeEventListener('storage', storage)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [check])
  if (blocked) return <main className="account-entry panel"><h1>Аккаунт изменился</h1><p>Локальные ответы сохранены в прежнем профиле.</p><button className="primary" onClick={() => window.location.reload()}>Открыть текущий аккаунт</button></main>
  if (!session) return <main className="account-entry panel" role="status">Открываем Academy AI…</main>
  if (session.mode === 'supabase' && !session.user) return <Login notice={notice || (offline ? 'Для входа нужно подключение к серверу.' : '')}/>
  return <SessionContext.Provider value={{session, offline}}>{children}</SessionContext.Provider>
}

export function AccountProfile() {
  const {session, offline} = useContext(SessionContext)
  const [pending, setPending] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  useEffect(() => {
    const load = () => { void listAttempts().then(rows => setPending(rows.filter(row => row.status !== 'synced').length)).catch(error => setNotice(message(error))) }
    load()
    window.addEventListener(OFFLINE_CHANGED, load)
    return () => window.removeEventListener(OFFLINE_CHANGED, load)
  }, [])
  async function pull() {
    setBusy(true)
    try {
      await synchronize()
      const snapshot = await api<{generated_at:string}>('/sync/snapshot')
      window.dispatchEvent(new Event('academy-sync-complete'))
      setNotice(`Прогресс получен с сервера ${new Date(snapshot.generated_at).toLocaleTimeString('ru-RU')}.`)
    } catch (error) { setNotice(message(error)) }
    finally { setBusy(false) }
  }
  async function logout() {
    setBusy(true)
    try {
      await api('/auth/logout', {})
      remember({mode:'supabase', user:null})
      window.location.reload()
    } catch (error) { setNotice(message(error)); setBusy(false) }
  }
  return <section className="panel settings-panel">
    <h2>Мой аккаунт</h2>
    {session.mode === 'local' ? <p>Локальный профиль. Для входа с разных устройств настрой Supabase Auth на сервере по инструкции V4.</p> : <><p>{session.user?.email || 'Сохранённый профиль на устройстве'}</p><p className="small-note">ID аккаунта {session.user?.id}</p><p>Для восстановления доступа на новом устройстве запроси код на этот же email.</p></>}
    <p role="status">{offline ? 'Офлайн. Ответы сохраняются на устройстве.' : 'Подключение к серверу подтверждено.'}</p>
    <p>Черновики и неотправленные результаты — {pending}</p>
    <div className="button-row"><button className="primary" disabled={busy || offline} onClick={pull}>Синхронизировать прогресс</button><a className="secondary" href="#offline">Ответы и экспорт</a><a className="secondary" href="#settings">Настройки</a></div>
    {session.mode === 'supabase' && <><p className="small-note">После выхода локальные ответы доступны при следующем входе в этот аккаунт. Перед выходом можно экспортировать их в библиотеке. Для выхода с отзывом сессии требуется сервер.</p><button className="secondary" disabled={busy || offline} onClick={logout}>Выйти из аккаунта</button></>}
    {notice && <p role="status">{notice}</p>}
  </section>
}
