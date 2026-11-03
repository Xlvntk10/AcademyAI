import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, CalendarDays, Check, CheckCircle2, Clock3, History, Settings2 } from 'lucide-react'
import { api } from './api'

export type StudySettings = { available_minutes: number[]; daily_goal_minutes: number; weekly_goal_minutes: number; reminder_enabled: boolean; reminder_time: string; timezone: string; english_percent: number }
export type Task = { id: string; scheduled_date: string; original_date: string; subject: 'english' | 'python'; kind: 'lesson' | 'review' | 'practice'; title: string; instructions: string; planned_minutes: number; status: string; actual_minutes: number | null; completed_at: string | null; lesson_slug: string | null; overdue: boolean }
export type Week = { week_start: string; today: string; generated: boolean; settings: StudySettings; tasks: Task[]; overdue: Task[]; planned_minutes: number; completed_minutes: number }
const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
export const localDay = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Almaty', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
export const addDays = (day: string, count: number) => { const d = new Date(`${day}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + count); return d.toISOString().slice(0, 10) }
export const weekStart = (day: string) => addDays(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7))
export const dateLabel = (day: string) => new Date(`${day}T12:00:00Z`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', timeZone: 'Asia/Almaty' })
export const message = (e: unknown) => e instanceof Error ? e.message : 'Не удалось сохранить изменения'

function TaskCard({ task, today, onChange }: { task: Task; today: string; onChange: () => void }) {
  const [minutes, setMinutes] = useState(task.planned_minutes)
  const [moveDate, setMoveDate] = useState(today)
  const [mode, setMode] = useState<'none' | 'complete' | 'move'>('none')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit() {
    setBusy(true); setError('')
    try {
      await api(`/planner/tasks/${task.id}/${mode === 'complete' ? 'complete' : 'reschedule'}`, mode === 'complete' ? { actual_minutes: minutes } : { scheduled_date: moveDate })
      setMode('none'); onChange()
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <article className={`task-card ${task.status === 'completed' ? 'task-completed' : ''}`}>
    <div className="task-card-heading"><span className={`subject-label ${task.subject}`}>{task.subject === 'english' ? 'English' : 'Python'}</span><span className="small-note"><Clock3 size={13} />{task.status === 'completed' ? task.actual_minutes : task.planned_minutes} мин</span>{task.status === 'completed' && <CheckCircle2 className="green" size={18} />}</div>
    <h3>{task.title}</h3><p>{task.instructions}</p>
    {task.original_date !== task.scheduled_date && <p className="small-note">Перенесено с {dateLabel(task.original_date)}</p>}
    <div className="task-actions">{task.lesson_slug && <a className="text-button" href={`#lesson/${task.lesson_slug}`}><BookOpen size={15} />Открыть урок</a>}
      {task.status === 'pending' && <><button className="text-button" onClick={() => { setMode(mode === 'move' ? 'none' : 'move'); setError('') }}>Перенести</button><button className="secondary compact" disabled={task.scheduled_date > today} onClick={() => { setMode(mode === 'complete' ? 'none' : 'complete'); setError('') }}><Check size={15} />Выполнено</button></>}
    </div>
    {mode !== 'none' && <form className="task-form" onSubmit={e => { e.preventDefault(); void submit() }}>
      {mode === 'complete' ? <label>Сколько минут ты занимался?<input type="number" min={1} max={480} required value={minutes} onChange={e => setMinutes(Number(e.target.value))} /></label> : <label>Новая дата<input type="date" min={today} max={addDays(today, 365)} required value={moveDate} onChange={e => setMoveDate(e.target.value)} /></label>}
      <button className="primary compact" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить'}</button><button type="button" className="text-button" disabled={busy} onClick={() => setMode('none')}>Отмена</button>
      {mode === 'complete' && <small>Время учитывается по твоей отметке. Для задания-урока сначала нужно закончить упражнения.</small>}
    </form>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </article>
}

export function DailyTasks({ onSaved }: { onSaved: () => void }) {
  const [week, setWeek] = useState<Week | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => { try { setWeek(await api<Week>('/planner/week')); setError('') } catch (e) { setError(message(e)) } }, [])
  useEffect(() => { void load() }, [load])
  if (error) return <div className="error-box" role="alert">{error}<button className="text-button" onClick={load}>Повторить</button></div>
  if (!week) return <div className="panel small-note" role="status">Загружаем задания…</div>
  const tasks = week.tasks.filter(t => t.scheduled_date === week.today)
  return <section className="daily-tasks"><div className="section-heading"><h2>Твои задания на сегодня</h2><a className="text-button" href="#plan">Весь план<ArrowRight size={16} /></a></div>
    {tasks.length ? tasks.map(task => <TaskCard key={task.id} task={task} today={week.today} onChange={() => { void load(); onSaved() }} />) : <div className="panel"><h3>{week.generated ? 'Сегодня свободный день' : 'Настроим твой ритм?'}</h3><p className="small-note">{week.generated ? 'Можно выбрать урок самостоятельно или отдохнуть.' : 'Выбери доступное время — и составь неделю английского и Python.'}</p><a href="#plan" className="text-button">Открыть план<ArrowRight size={16} /></a></div>}
    {week.overdue.length > 0 && <a className="overdue-note" href="#plan">Невыполненных заданий из прошлых дней: {week.overdue.length}. Можно перенести их в плане.</a>}
  </section>
}

export default function Planner({ onSaved }: { onSaved: () => void }) {
  const [start, setStart] = useState(() => weekStart(localDay()))
  const [selected, setSelected] = useState(localDay)
  const [week, setWeek] = useState<Week | null>(null)
  const [settings, setSettings] = useState<StudySettings | null>(null)
  const [editing, setEditing] = useState(false)
  const [history, setHistory] = useState<Task[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(async () => {
    setLoading(true)
    try { const data = await api<Week>(`/planner/week?start=${start}`); setWeek(data); setSettings(data.settings); setError('') }
    catch (e) { setError(message(e)) } finally { setLoading(false) }
  }, [start])
  useEffect(() => { void load() }, [load])
  function shift(offset: number) { const next = addDays(start, offset); setStart(next); setSelected(next); setHistory(null) }
  async function generate(replace = false) {
    setBusy(true); setError(''); setNotice('')
    try { setWeek(await api<Week>('/planner/generate', { week_start: start, replace_pending: replace })); setNotice(replace ? 'Будущие невыполненные задания обновлены. История сохранена.' : 'Неделя готова. Начни с небольшого шага.'); onSaved() }
    catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  async function saveSettings() {
    if (!settings) return
    setBusy(true); setError('')
    try {
      const { timezone: _zone, english_percent: _ratio, ...payload } = settings
      setSettings(await api<StudySettings>('/planner/settings', payload)); setEditing(false)
      setNotice('Настройки сохранены. Нажми «Обновить задания», чтобы применить их к уже созданной неделе.')
      await load(); onSaved()
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  async function showHistory() { try { setHistory(history ? null : await api<Task[]>('/planner/history')); setError('') } catch (e) { setError(message(e)) } }
  const changed = () => { void load(); if (history) void api<Task[]>('/planner/history').then(setHistory).catch(e => setError(message(e))); onSaved() }
  return <><div className="page-intro"><p>Твой горизонт — 2028</p><h2>Большая цель. Реальный план.</h2><span>65% английского · 35% программирования · время Asia/Almaty</span></div>
    {error && <div className="error-box" role="alert">{error}<button className="text-button" onClick={load}>Повторить</button></div>}{notice && <p className="success-note" role="status">{notice}</p>}
    <div className="planner-controls"><div className="week-nav"><button className="icon-button" aria-label="Предыдущая неделя" disabled={loading || busy} onClick={() => shift(-7)}><ArrowLeft size={18} /></button><strong>{dateLabel(start)} — {dateLabel(addDays(start, 6))}</strong><button className="icon-button" aria-label="Следующая неделя" disabled={loading || busy} onClick={() => shift(7)}><ArrowRight size={18} /></button></div><div className="button-row"><button className="secondary compact" onClick={() => setEditing(!editing)}><Settings2 size={16} />Расписание</button><button className="secondary compact" onClick={showHistory}><History size={16} />История</button></div></div>
    {editing && settings && <form className="panel settings-panel" onSubmit={e => { e.preventDefault(); void saveSettings() }}><h3>Время для занятий</h3><p className="small-note">Минут в день. 0 — выходной. Изменения не затрагивают выполненные задания.</p><div className="availability-grid">{days.map((day, i) => <label key={day}>{day}<input type="number" min={0} max={480} required value={settings.available_minutes[i]} onChange={e => setSettings({ ...settings, available_minutes: settings.available_minutes.map((n, j) => i === j ? Number(e.target.value) : n) })} /></label>)}</div>
      <div className="settings-goals"><label>Цель за день, мин<input type="number" min={5} max={480} required value={settings.daily_goal_minutes} onChange={e => setSettings({ ...settings, daily_goal_minutes: Number(e.target.value) })} /></label><label>Цель за неделю, мин<input type="number" min={5} max={3360} required value={settings.weekly_goal_minutes} onChange={e => setSettings({ ...settings, weekly_goal_minutes: Number(e.target.value) })} /></label></div>
      <button className="primary" disabled={busy}>Сохранить расписание</button></form>}
    {loading ? <div className="loading" role="status">Загружаем неделю…</div> : week && <>
      <div className="week-calendar" aria-label="Дни недели">{days.map((day, i) => { const date = addDays(start, i); const tasks = week.tasks.filter(t => t.scheduled_date === date); const planned = tasks.reduce((sum, t) => sum + t.planned_minutes, 0); return <button key={day} aria-pressed={selected === date} onClick={() => setSelected(date)} className={`calendar-day ${selected === date ? 'selected' : ''} ${date === week.today ? 'is-today' : ''}`}><span>{day}</span><strong>{Number(date.slice(8))}</strong><small>{planned ? `${planned} мин` : 'Свободно'}</small><span className="calendar-dots">{tasks.some(t => t.subject === 'english') && <i className="english" />}{tasks.some(t => t.subject === 'python') && <i className="python" />}{tasks.length > 0 && tasks.every(t => t.status === 'completed') && <Check size={13} />}</span></button> })}</div>
      <div className="planner-summary"><p><b>{week.planned_minutes}</b> мин запланировано · <b>{week.completed_minutes}</b> мин выполнено</p>{start >= weekStart(week.today) && <button className="primary compact" disabled={busy} onClick={() => generate(week.generated)}>{busy ? 'Составляем…' : week.generated ? 'Обновить задания' : 'Составить неделю'}</button>}</div>
      {history ? <section><div className="section-heading"><h2>История выполненных заданий</h2><button className="text-button" onClick={() => setHistory(null)}>Закрыть</button></div>{history.length ? history.map(task => <div key={task.id}><p className="small-note">{task.completed_at && new Date(task.completed_at).toLocaleString('ru-RU', { timeZone: 'Asia/Almaty' })}</p><TaskCard task={task} today={week.today} onChange={changed} /></div>) : <div className="panel small-note">Выполненные задания появятся здесь после твоей отметки.</div>}</section> : <><div className="section-heading"><h2>{dateLabel(selected)}{selected === week.today ? ' · Сегодня' : ''}</h2></div><div className="task-list">{week.tasks.filter(t => t.scheduled_date === selected).map(task => <TaskCard key={task.id} task={task} today={week.today} onChange={changed} />)}{!week.tasks.some(t => t.scheduled_date === selected) && <div className="panel empty-state"><CalendarDays size={28} /><h3>{week.generated ? 'Можно выдохнуть' : 'Твоя неделя ещё не составлена'}</h3><p>{week.generated ? 'На этот день нет заданий. Выбери урок самостоятельно или оставь время для отдыха.' : 'Проверь расписание и нажми «Составить неделю».'}</p></div>}</div></>}
      {week.overdue.length > 0 && <section className="overdue-section"><div className="section-heading"><h2>Можно вернуться и продолжить</h2><span className="small-note">Пропущенные задания</span></div>{week.overdue.map(task => <div key={task.id}><p className="small-note">Было запланировано на {dateLabel(task.scheduled_date)}</p><TaskCard task={task} today={week.today} onChange={changed} /></div>)}</section>}
    </>}
  </>
}
