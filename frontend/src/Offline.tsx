import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, RefreshCw, WifiOff } from 'lucide-react'
import { api, type Lesson } from './api'
import CodeBlock from './CodeBlock'
import { message } from './Planner'
import { listBundles, listAttempts, saveBundle, startOffline, saveDraft, queueAttempt, retryAttempt,
  OFFLINE_CHANGED, type OfflineBundle, type OfflineAttempt } from './offline-store'
import { synchronize, syncStatus } from './offline-sync'
import { offlineShellReady } from './pwa'

export function OfflineLanding() {
  const [bundles, setBundles] = useState<OfflineBundle[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { void listBundles().then(setBundles).catch(e => setError(message(e))) }, [])
  return <section className="panel offline-tools"><WifiOff size={24}/><h2>Учёба без подключения</h2>
    {error ? <p role="alert">{error}</p> : bundles === null ? <p>Открываем локальную библиотеку…</p> : bundles.length ? <>
      <p>На устройстве доступны скачанные уроки. Черновики и очередь ответов можно открыть в локальной библиотеке.</p>
      <div className="offline-cards">{bundles.map(bundle => <a className="offline-lesson" key={bundle.lesson.slug} href="#offline"><strong>{bundle.lesson.title}</strong><span>{bundle.lesson.level} · версия {bundle.lesson.version}</span></a>)}</div>
    </> : <p>Скачанных уроков пока нет. Подключись к домашнему серверу и нажми «Скачать урок», чтобы подготовить занятия для работы без сети.</p>}
    <a className="secondary" href="#offline">Локальная библиотека и мои ответы</a>
  </section>
}

export function DownloadLesson({ slug }: { slug: string }) {
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  async function download() {
    setBusy(true); setNotice('')
    try {
      await saveBundle(await api<OfflineBundle>(`/offline/lessons/${slug}`))
      setNotice('Урок сохранён на этом устройстве.')
    } catch (error) { setNotice(message(error)) } finally { setBusy(false) }
  }
  return <div className="offline-download"><button className="secondary" disabled={busy} onClick={download}><Download size={17}/>{busy ? 'Сохраняем…' : 'Скачать урок'}</button>{notice && <span role="status">{notice} <a href="#offline">Локальная библиотека</a></span>}</div>
}

export function SyncStatus() {
  const [attempts, setAttempts] = useState<OfflineAttempt[]>([])
  const [status, setStatus] = useState(syncStatus)
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(navigator.onLine)
  useEffect(() => {
    const refresh = () => { void listAttempts().then(setAttempts).catch(e => setError(message(e))); setStatus(syncStatus()) }
    const online = () => { setConnected(navigator.onLine); void synchronize() }
    const visible = () => { if (document.visibilityState === 'visible') { refresh(); void synchronize() } }
    const storage = (event: StorageEvent) => { if (event.key === 'academy-offline-pulse') refresh() }
    refresh(); void synchronize()
    window.addEventListener(OFFLINE_CHANGED, refresh)
    window.addEventListener('academy-sync-state', refresh)
    window.addEventListener('online', online); window.addEventListener('offline', online)
    window.addEventListener('academy-account-connected', visible)
    window.addEventListener('storage', storage); document.addEventListener('visibilitychange', visible)
    const timer = window.setInterval(visible, 60000)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener(OFFLINE_CHANGED, refresh); window.removeEventListener('academy-sync-state', refresh)
      window.removeEventListener('online', online); window.removeEventListener('offline', online)
      window.removeEventListener('academy-account-connected', visible)
      window.removeEventListener('storage', storage); document.removeEventListener('visibilitychange', visible)
    }
  }, [])
  const pending = attempts.filter(a => a.status === 'queued').length
  const conflicts = attempts.filter(a => a.status === 'conflict').length
  const label = status.state === 'syncing' ? 'Отправляем ответы…' : !connected || status.state === 'unavailable' ? 'Ожидаем связь с сервером' : 'Локальная библиотека'
  return <div className="sync-strip" aria-live="polite"><a href="#offline"><WifiOff size={17}/>{label}</a>
    {pending > 0 && <span>В очереди {pending}</span>}{conflicts > 0 && <a href="#offline">Требуют внимания {conflicts}</a>}
    {pending > 0 && <button className="text-button" disabled={status.state === 'syncing'} onClick={() => void synchronize()}>Отправить</button>}
    {(error || status.state === 'error') && <span role="alert">{error || status.detail}</span>}</div>
}

function OfflinePractice({ initial, onExit }: { initial: OfflineAttempt; onExit: () => void }) {
  const [attempt, setAttempt] = useState(initial)
  const [answers, setAnswers] = useState(initial.answers)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const revision = useRef(initial.revision)
  const failed = useRef(false)
  const writes = useRef(Promise.resolve())
  const lesson = attempt.bundle.lesson
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (saving || failed.current) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [saving])
  function change(id: number, value: string) {
    const next = { ...answers, [id]: value }
    setAnswers(next); setSaving(true)
    writes.current = writes.current.then(async () => {
      if (failed.current) return
      const saved = await saveDraft(attempt.id, revision.current, next)
      revision.current = saved.revision
      setAttempt(saved)
    }).catch(e => { failed.current = true; setError(message(e)) })
    const latest = writes.current
    void latest.then(() => { if (writes.current === latest) setSaving(false) })
  }
  async function finish() {
    setBusy(true)
    try {
      await writes.current
      if (failed.current) return
      setAttempt(await queueAttempt(attempt.id, revision.current))
      void synchronize()
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <section className="offline-practice"><button className="text-button" onClick={onExit} disabled={saving || busy}>К локальной библиотеке</button>
    <h2>{lesson.title}</h2><p className="small-note">Ответы сохраняются на этом устройстве. Сервер проверит их после отправки. XP появится после подтверждения.</p>
    {error && <div className="error-box" role="alert">{error}</div>}
    {attempt.status === 'draft' ? <><div role="status">{saving ? 'Сохраняем на устройстве…' : failed.current ? 'Сохранение требует внимания' : 'Черновик сохранён на устройстве'}</div>
      <form onSubmit={e => { e.preventDefault(); void finish() }}>
        {lesson.exercises.map((exercise, index) => <fieldset className="panel offline-question" key={exercise.id} disabled={busy || failed.current}>
          <legend>{index + 1}. {exercise.question}</legend>
          {exercise.kind === 'choice' ? exercise.options.map(option => <label className="offline-option" key={option}><input type="radio" name={`offline-${exercise.id}`} value={option} checked={answers[exercise.id] === option} onChange={() => change(exercise.id, option)}/>{option}</label>) : <label>Твой ответ<input maxLength={500} autoComplete="off" value={answers[exercise.id] ?? ''} onChange={event => change(exercise.id, event.target.value)} /></label>}
        </fieldset>)}
        <button className="primary" disabled={saving || busy || failed.current || lesson.exercises.some(e => !answers[e.id]?.trim())}>Завершить и поставить в очередь</button>
      </form></> : <div className="panel"><h3>Ответы в очереди</h3><p>Можно закрыть приложение. Отправка продолжится при следующем открытии и доступном сервере.</p><button className="primary" onClick={onExit}>К библиотеке и результатам</button></div>}
  </section>
}

function exportAttempts(attempts: OfflineAttempt[]) {
  const blob = new Blob([JSON.stringify({ format: 'academy-offline-export-v1', exported_at: new Date().toISOString(), attempts }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = `academy-offline-${new Date().toISOString().slice(0, 10)}.json`; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function OfflineLibrary({ lessons }: { lessons: Lesson[] }) {
  const [bundles, setBundles] = useState<OfflineBundle[]>([])
  const [attempts, setAttempts] = useState<OfflineAttempt[]>([])
  const [selected, setSelected] = useState<OfflineBundle | null>(null)
  const [active, setActive] = useState<OfflineAttempt | null>(null)
  const [slug, setSlug] = useState('')
  const [error, setError] = useState('')
  const [storageNotice, setStorageNotice] = useState('')
  const [shellReady, setShellReady] = useState(offlineShellReady)
  const refresh = useCallback(async () => {
    try {
      const [saved, runs] = await Promise.all([listBundles(), listAttempts()])
      setBundles(saved); setAttempts(runs)
      setSelected(current => current ? saved.find(bundle => bundle.lesson.slug === current.lesson.slug) ?? current : null)
    }
    catch (e) { setError(message(e)) }
  }, [])
  useEffect(() => {
    void refresh()
    const shell = () => setShellReady(offlineShellReady())
    window.addEventListener('academy-shell-status', shell)
    const storage = (event: StorageEvent) => { if (event.key === 'academy-offline-pulse') void refresh() }
    window.addEventListener(OFFLINE_CHANGED, refresh); window.addEventListener('storage', storage)
    return () => { window.removeEventListener(OFFLINE_CHANGED, refresh); window.removeEventListener('storage', storage); window.removeEventListener('academy-shell-status', shell) }
  }, [refresh])
  async function start(bundle: OfflineBundle) {
    try { setActive(await startOffline(bundle)); setError('') } catch (e) { setError(message(e)) }
  }
  async function persistStorage() {
    try { setStorageNotice(await navigator.storage.persist() ? 'Браузер разрешил постоянное хранение. Резервную копию ответов можно скачать ниже.' : 'Браузер пока не разрешил постоянное хранение. Скачивай копию важных ответов.') }
    catch (e) { setStorageNotice(message(e)) }
  }
  if (active) return <OfflinePractice key={active.id} initial={active} onExit={() => { setActive(null); void refresh() }}/>
  return <div className="offline-library"><div className="page-intro"><p>На этом устройстве</p><h2>Учись в своём ритме. Даже без сети.</h2><span>Скачай урок заранее, сохрани ответы и отправь их, когда домашний сервер снова доступен.</span></div>
    {error && <div className="error-box" role="alert">{error}</div>}
    <p className="small-note" role="status">{shellReady ? 'Service Worker подтвердил наличие оболочки в кеше. Проверь автономный запуск на своём устройстве перед поездкой.' : 'Кеш оболочки пока не подтверждён. Для повторного открытия без сети нужна production-версия по HTTPS или localhost. Дождись подготовки кеша, затем проверь открытие без сети.'}</p>
    <section className="panel offline-tools"><h3>Сохранённые уроки</h3>
      {lessons.length > 0 && <div className="button-row"><label>Выбрать урок<select value={slug} onChange={event => setSlug(event.target.value)}><option value="">Выбери урок</option>{lessons.map(l => <option key={l.slug} value={l.slug}>{l.level} · {l.title}</option>)}</select></label>{slug && <DownloadLesson key={slug} slug={slug}/>}</div>}
      {bundles.length === 0 && <p>Здесь появятся скачанные уроки. При доступном сервере открой урок и нажми «Скачать урок».</p>}
      <div className="offline-cards">{bundles.map(bundle => <button className="offline-lesson" key={bundle.lesson.slug} onClick={() => setSelected(bundle)}><strong>{bundle.lesson.title}</strong><span>{bundle.lesson.level} · версия {bundle.lesson.version} · {bundle.lesson.exercise_count} заданий</span></button>)}</div>
    </section>
    {selected && <section className="panel offline-theory"><h2>{selected.lesson.title}</h2>{selected.lesson.theory.map(block => <div key={block.title}><h3>{block.title}</h3><p>{block.body}</p>{block.code && <CodeBlock code={block.code}/>}<div className="examples">{block.examples.map(example => <p key={example}>{example}</p>)}</div></div>)}
      <p className="small-note">Сохранено {new Date(selected.downloaded_at).toLocaleString('ru-RU')}. После обновления урока старые ответы остаются в локальной истории.</p>
      {selected.lesson.unlocked === false && <p>Для практики освой предыдущие темы на сервере и скачай урок заново.</p>}
      <div className="button-row"><button className="primary" disabled={selected.lesson.unlocked === false} onClick={() => void start(selected)}>Практика на устройстве</button><DownloadLesson slug={selected.lesson.slug}/></div></section>}
    <section className="panel offline-history"><div className="section-heading"><h3>Ответы и отправка</h3><button className="text-button" onClick={() => void synchronize()}><RefreshCw size={16}/>Отправить очередь</button></div>
      {attempts.length === 0 && <p>Локальных попыток пока нет.</p>}
      {[...attempts].sort((a, b) => b.startedAt.localeCompare(a.startedAt)).map(attempt => <article key={attempt.id} className="offline-attempt"><h4>{attempt.bundle.lesson.title}</h4><p>{new Date(attempt.startedAt).toLocaleString('ru-RU')} · версия {attempt.bundle.lesson.version}</p>
        <strong>{attempt.status === 'draft' ? 'Черновик на устройстве' : attempt.status === 'queued' ? 'Ожидает проверки сервера' : attempt.status === 'conflict' ? 'Отправка требует внимания' : `Подтверждено сервером · ${attempt.result?.score} / ${attempt.result?.max_score} баллов`}</strong>
        {attempt.error && <p role="alert">{attempt.error}</p>}
        {attempt.status === 'draft' && <button className="secondary" onClick={() => setActive(attempt)}>Продолжить черновик</button>}
        {attempt.status === 'conflict' && <button className="secondary" onClick={() => void retryAttempt(attempt.id).then(() => synchronize()).catch(e => setError(message(e)))}>Повторить отправку исходной попытки</button>}
        <details><summary>Мои ответы{attempt.result ? ' и объяснения' : ''}</summary>{attempt.bundle.lesson.exercises.map(exercise => { const checked = attempt.result?.answers.find(a => a.exercise_id === exercise.id); return <div key={exercise.id}><p><strong>{exercise.question}</strong></p><p>{attempt.answers[exercise.id] || 'Ответ ещё не сохранён'}</p>{checked && <p>{checked.is_correct ? 'Верно.' : `Правильный ответ — ${checked.correct_answer}.`} {checked.explanation}</p>}</div> })}</details>
      </article>)}
    </section>
    <section className="panel offline-tools"><h3>Хранение на устройстве</h3><p>Ответы хранятся в профиле этого браузера. Очистка данных сайта удаляет локальные копии. Используй личное устройство и скачивай резервную копию важных ответов.</p><div className="button-row">{typeof navigator.storage?.persist === 'function' && <button className="secondary" onClick={() => void persistStorage()}>Закрепить локальное хранение</button>}<button className="secondary" disabled={!attempts.length} onClick={() => exportAttempts(attempts)}>Скачать копию ответов JSON</button></div>{storageNotice && <p role="status">{storageNotice}</p>}</section>
  </div>
}
