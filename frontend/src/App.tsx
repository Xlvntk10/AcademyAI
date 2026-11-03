import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, CalendarDays, Check, CheckCircle2, ChevronRight, Circle, Clock3, GraduationCap, Leaf, LoaderCircle, Moon, RefreshCw, Settings2, Sparkles, Sun, TrendingUp, Trophy, X, Zap } from 'lucide-react'
import { api, newRequestId, type Lesson, type LessonDetail, type Progress, type Run } from './api'
import Planner, { DailyTasks } from './Planner'
import Analytics, { Motivation } from './Analytics'
import Curriculum from './Curriculum'
import CodeBlock from './CodeBlock'
import Settings, { ReminderHost } from './Settings'
import Vocabulary from './Vocabulary'

type Section = 'today' | 'learn' | 'plan' | 'progress'
const sections = [
  { id: 'today', label: 'Сегодня', icon: Sun },
  { id: 'learn', label: 'Обучение', icon: BookOpen },
  { id: 'plan', label: 'План', icon: CalendarDays },
  { id: 'progress', label: 'Прогресс', icon: TrendingUp },
] as const
const titles = { today: 'Твой новый маленький шаг', learn: 'Знания, которые остаются', plan: 'Большая цель. Маленькие шаги.', progress: 'Каждый шаг имеет значение' }
const readRoute = () => window.location.hash.slice(1) || 'today'
const navigate = (route: string) => { window.location.hash = route }
const prettyDate = (date: string) => new Date(date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', timeZone: 'Asia/Almaty' })
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Что-то пошло не так. Попробуй ещё раз.'

function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-box" role="alert"><span>{message}</span>{retry && <button className="text-button" onClick={retry}><RefreshCw size={16} />Повторить</button>}</div>
}

function Loading() {
  return <div className="loading" role="status"><LoaderCircle className="spin" />Загружаем твоё пространство…</div>
}

function LessonCard({ lesson, progress, onOpen }: { lesson: Lesson; progress: Progress; onOpen: () => void }) {
  const stats = progress.lessons.find(item => item.slug === lesson.slug)
  return <article className="lesson-card">
    <div className="course-art" aria-hidden="true"><span className="art-ring" /><span className="art-dot" /><div className="letter-tile">{lesson.subject === 'python' ? '</>' : 'Aa'}<span>{lesson.subject === 'python' ? 'PYTHON' : 'ENGLISH'}</span></div><span className="small-spark">✦</span></div>
    <div className="lesson-card-content"><div className="eyebrow green">{lesson.subject === 'python' ? 'PYTHON' : 'АНГЛИЙСКИЙ'} <span className="level">{lesson.level}</span></div>
      <h3>{lesson.title}</h3><p>{lesson.summary}</p>
      <div className="metadata"><span><Clock3 size={15} />{lesson.duration_minutes} минут</span><span><BookOpen size={15} />{lesson.exercise_count} заданий</span></div>
      <div className="card-bottom"><span className="small-note">{stats?.completed_runs ? `Лучший результат: ${stats.best_score}/${stats.max_score}` : stats?.active_run_id ? 'Урок начат — продолжим?' : 'Готов к новому шагу?'}</span>
        <button className="primary compact" onClick={onOpen}>{stats?.completed_runs ? 'Открыть' : stats?.active_run_id ? 'Продолжить' : 'Начать'}<ArrowRight size={17} /></button></div>
    </div>
  </article>
}

function Today({ lessons, progress, onSaved }: { lessons: Lesson[]; progress: Progress; onSaved: () => void }) {
  const first = lessons.find(l => !progress.lessons.find(p => p.slug === l.slug)?.completed_runs) ?? lessons[0]
  const complete = first && progress.lessons.find(s => s.slug === first.slug)?.completed_runs
  return <div className="dashboard-grid"><div className="main-column">
    <section className="welcome-card"><div><span className="eyebrow"><span className="tiny-dot" /> МЕСТО ДЛЯ ТВОЕГО РОСТА</span><h2>Большое начинается<br />с маленького.</h2><p>Немного английского сегодня.<br />Больше возможностей завтра.</p>
      {first && <button className="primary" onClick={() => navigate(`lesson/${first.slug}`)}>{complete ? 'Повторить урок' : 'Продолжить обучение'}<ArrowRight size={18} /></button>}</div>
      <div className="growth-art" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="orbit-dot" /><div className="growth-book"><Leaf size={50} strokeWidth={1.4} /><span>grow a little<br />every day.</span></div><span className="floating-badge"><Sparkles size={20} /></span></div>
    </section>
    <div className="section-heading"><h2>Продолжим учиться</h2><button className="text-button" onClick={() => navigate('learn')}>Все уроки<ArrowRight size={16} /></button></div>
    {first ? <LessonCard lesson={first} progress={progress} onOpen={() => navigate(`lesson/${first.slug}`)} /> : <div className="panel">Уроки ещё не добавлены.</div>}
    <DailyTasks onSaved={onSaved} />
    <div className="note-strip"><span className="note-icon"><Leaf size={19} /></span><div><strong>В своём ритме</strong><p>Не нужно знать всё сразу. Достаточно возвращаться и пробовать.</p></div></div>
  </div><aside className="right-column">
    <Motivation progress={progress} />
    <section className="panel focus-panel"><div className="section-heading"><h3>Фокус на сегодня</h3><Sun size={19} className="muted" /></div><p className="small-note">Предложение для следующего шага</p>
      <div className="focus-task"><span className={`task-check ${complete ? 'done' : ''}`}>{complete ? <Check size={16} /> : <Circle size={16} />}</span><div><strong>{first ? first.title : 'Выбрать направление'}</strong><p>{first ? `${first.subject === 'python' ? 'Python' : 'Английский'} · ${first.level} · ${first.duration_minutes} минут` : 'Новые уроки появятся в обучении'}</p></div></div>
      <p className="focus-foot">{complete ? 'Можно повторить и улучшить результат.' : 'Одна небольшая практика — уже движение вперёд.'}</p>
    </section>
    <section className="panel journey-panel"><span className="stat-icon lilac"><GraduationCap size={22} /></span><span className="eyebrow">ТВОЙ ОРИЕНТИР</span><h3>Магистратура<br />в 2028</h3><p>Английский, программирование и уверенность в своих знаниях.</p><button className="text-button" onClick={() => navigate('plan')}>Посмотреть направление<ArrowRight size={16} /></button></section>
    <section className="mini-progress"><div><Zap size={18} /><strong>{progress.total_xp} XP</strong></div><p>Уроки и регулярная<br />самостоятельная практика</p></section>
  </aside></div>
}

export function LessonPlayer({ slug, onSaved, onExit, catalogue = [] }: { slug: string; onSaved: () => void; onExit: () => void; catalogue?: Lesson[] }) {
  const [lesson, setLesson] = useState<LessonDetail | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [stage, setStage] = useState<'theory' | 'exercise' | 'result'>('theory')
  const [index, setIndex] = useState(0)
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [requestId, setRequestId] = useState(newRequestId)
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [detail, stats] = await Promise.all([api<LessonDetail>(`/lessons/${slug}`), api<Progress>(`/progress`)])
      const lessonStats = stats.lessons.find(s => s.slug === slug)
      const existing = lessonStats?.active_run_id ? await api<Run>(`/runs/${lessonStats.active_run_id}`) : lessonStats?.last_result ?? null
      setLesson(detail); setRun(existing)
      if (existing?.completed_at) setStage('result')
      else if (existing) {
        setIndex(Math.max(0, detail.exercises.findIndex(e => !existing.answers.some(a => a.exercise_id === e.id))))
        setStage('exercise')
      } else setStage('theory')
    } catch (e) { setError(errorMessage(e)) }
    finally { setLoading(false) }
  }, [slug])
  useEffect(() => { void load() }, [load])

  async function begin() {
    if (!lesson) return
    setBusy(true); setError('')
    try {
      const result = await api<Run>(`/lessons/${slug}/runs`, { request_id: requestId })
      setRun(result)
      setIndex(Math.max(0, lesson.exercises.findIndex(e => !result.answers.some(a => a.exercise_id === e.id))))
      setAnswer(''); setStage(result.completed_at ? 'result' : 'exercise'); onSaved()
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  async function submit() {
    if (!lesson || !run || !answer.trim()) return
    setBusy(true); setError('')
    try {
      setRun(await api<Run>(`/runs/${run.id}/answers`, { exercise_id: lesson.exercises[index].id, answer }))
      onSaved()
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  function next() {
    if (run?.completed_at) setStage('result')
    else {
      setIndex(lesson!.exercises.findIndex(e => !run?.answers.some(a => a.exercise_id === e.id)))
      setAnswer('')
    }
  }
  function repeat() { setRequestId(newRequestId()); setRun(null); setAnswer(''); setStage('theory'); setError('') }
  if (loading) return <Loading />
  if (!lesson) return <><button className="text-button" onClick={onExit}><ArrowLeft size={17} />К урокам</button><ErrorBox message={error} retry={load} /></>
  const nextLesson = catalogue.filter(l => l.subject === lesson.subject && l.position > lesson.position).sort((a,b) => a.position-b.position)[0]
  const exercise = lesson.exercises[index]
  const feedback = run?.answers.find(a => a.exercise_id === exercise?.id)
  return <div className="lesson-player"><div className="lesson-toolbar"><button className="text-button" onClick={onExit}><ArrowLeft size={17} />К урокам</button><span className="tag">{lesson.subject === 'python' ? 'Python' : 'English'} · {lesson.level}</span></div>
    {error && <ErrorBox message={error} />}
    {stage === 'theory' && <><div className="lesson-title"><span className="eyebrow green">МАЛЕНЬКИЕ ПРИВЫЧКИ, БОЛЬШИЕ ПЕРЕМЕНЫ</span><h2>{lesson.title}</h2><p>{lesson.summary}</p><div className="metadata"><span><Clock3 size={16} />{lesson.duration_minutes} минут</span><span><BookOpen size={16} />{lesson.exercise_count} упражнений</span><span><Zap size={16} />До {lesson.max_score} XP</span></div></div>
      <div className="theory-list">{lesson.theory.map((block, i) => <section className="theory-block" key={block.title}><span className="theory-number">{String(i + 1).padStart(2, '0')}</span><div><h3>{block.title}</h3><p>{block.body}</p>{block.code && <CodeBlock code={block.code} />}<div className="examples">{block.examples.map(example => <p key={example}>{example}</p>)}</div></div></section>)}</div>
      <div className="practice-start"><div><h3>Попробуем на практике?</h3><p>После каждого ответа — объяснение. Ошибаться можно.</p></div><button className="primary" disabled={busy} onClick={begin}>{busy ? 'Открываем…' : run ? 'Продолжить практику' : 'Начать практику'}<ArrowRight size={18} /></button></div>
    </>}
    {stage === 'exercise' && exercise && <><div className="exercise-top"><span>Упражнение {index + 1} из {lesson.exercise_count}</span><span>{run?.score ?? 0} / {lesson.max_score} баллов</span></div><div className="progress-track" role="progressbar" aria-label="Выполненные упражнения" aria-valuenow={run?.answered_count ?? 0} aria-valuemin={0} aria-valuemax={lesson.exercise_count}><span style={{ width: `${(run?.answered_count ?? 0) / lesson.exercise_count * 100}%` }} /></div>
      <form className="exercise-panel" onSubmit={e => { e.preventDefault(); if (feedback) next(); else void submit() }}><span className="exercise-symbol"><BookOpen size={27} /></span><span className="eyebrow green">{exercise.kind === 'choice' ? 'ВЫБЕРИ ОДИН ОТВЕТ' : 'НАПИШИ СВОЙ ОТВЕТ'}</span><h2>{exercise.question}</h2>
        {exercise.kind === 'choice' ? <fieldset className="options" disabled={busy || !!feedback}><legend className="sr-only">Варианты ответа</legend>{exercise.options.map((option, i) => <label key={option} className={`option ${(feedback?.answer ?? answer) === option ? 'selected' : ''}`}><input type="radio" name={`exercise-${exercise.id}`} value={option} checked={(feedback?.answer ?? answer) === option} onChange={() => setAnswer(option)} /><span className="option-number">{i + 1}</span><span>{option}</span><span className="option-radio" /></label>)}</fieldset> : <label className="text-answer">Твой ответ<input autoComplete="off" autoCapitalize={lesson.subject === 'python' ? 'none' : 'sentences'} spellCheck={lesson.subject !== 'python'} maxLength={500} placeholder={lesson.subject === 'python' ? 'Введи точный ответ. Регистр важен.' : 'Напиши по-английски…'} value={feedback?.answer ?? answer} onChange={e => setAnswer(e.target.value)} disabled={busy || !!feedback} /></label>}
        {feedback && <div className={`feedback ${feedback.is_correct ? 'correct' : 'incorrect'}`} role="status"><div>{feedback.is_correct ? <CheckCircle2 size={23} /> : <BookOpen size={23} />}<strong>{feedback.is_correct ? `Верно! +${feedback.earned_points} баллов` : 'Ещё один момент стал понятнее'}</strong></div>{!feedback.is_correct && <p>Правильный ответ: <b>{feedback.correct_answer}</b></p>}<p>{feedback.explanation}</p><small><Check size={14} />Ответ сохранён</small></div>}
        <div className="exercise-actions"><button type="button" className="text-button" onClick={() => setStage('theory')} disabled={busy}><BookOpen size={16} />К теории</button><button className="primary" type="submit" disabled={busy || (!feedback && !answer.trim())}>{busy ? 'Проверяем…' : feedback ? run?.completed_at ? 'Посмотреть результат' : 'Дальше' : 'Проверить ответ'}<ArrowRight size={17} /></button></div>
      </form></>}
    {stage === 'result' && run && <><section className="result-hero"><span className="trophy-circle"><Trophy size={43} /></span><span className="eyebrow green">ЕЩЁ ОДИН ШАГ ВПЕРЁД</span><h2>Урок завершён!</h2><p>{run.score === run.max_score ? 'Отлично! Все ответы верные.' : 'Хорошая практика. Разбери ответы и возвращайся, когда захочешь.'}</p><div className="result-numbers"><div><strong>{run.score}<small>/{run.max_score}</small></strong><span>Баллов за прохождение</span></div><div><strong>{run.correct_count}<small>/{run.exercise_count}</small></strong><span>Правильных ответов</span></div></div><p className="saved-note"><CheckCircle2 size={16} />Результат сохранён · {run.completed_at && prettyDate(run.completed_at)}</p><div className="result-buttons">{nextLesson && <a className="primary" href={`#lesson/${nextLesson.slug}`}>Следующий урок<ArrowRight size={17} /></a>}<button className="primary" onClick={onExit}>К обучению<ArrowRight size={17} /></button><button className="secondary" onClick={repeat}><RefreshCw size={17} />Повторить урок</button></div></section>
      <div className="section-heading"><h3>Разбор ответов</h3><span className="small-note">Можно возвращаться в любое время</span></div><div className="review-list">{run.answers.map((item, i) => <details key={item.exercise_id}><summary><span className={item.is_correct ? 'review-correct' : 'review-incorrect'}>{item.is_correct ? <Check size={18} /> : <X size={18} />}</span><span>{lesson.exercises.find(e => e.id === item.exercise_id)?.question ?? `Задание ${i + 1}`}</span><ChevronRight size={17} /></summary><div><p>Твой ответ: <strong>{item.answer}</strong></p>{!item.is_correct && <p>Правильный ответ: <strong>{item.correct_answer}</strong></p>}<p>{item.explanation}</p></div></details>)}</div>
    </>}
  </div>
}

export default function App() {
  const [route, setRoute] = useState(readRoute)
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light')
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [progress, setProgress] = useState<Progress | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    try {
      const [items, stats] = await Promise.all([api<Lesson[]>('/lessons'), api<Progress>('/progress')])
      setLessons(items); setProgress(stats); setError('')
    } catch (e) { setError(errorMessage(e)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const onChange = () => { setRoute(readRoute()); window.scrollTo({ top: 0, behavior: 'instant' }); void refresh() }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [refresh])
  function toggleTheme() {
    const value = theme === 'dark' ? 'light' : 'dark'
    setTheme(value); document.documentElement.dataset.theme = value
    try { localStorage.setItem('academy-theme', value) } catch { /* Theme works even when storage is unavailable. */ }
  }
  const lessonSlug = route.startsWith('lesson/') ? route.slice(7) : null
  const section: Section | null = sections.some(s => s.id === route) ? route as Section : route === 'settings' ? null : 'learn'
  const today = new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long', timeZone: 'Asia/Almaty' })
  return <div className="app-shell"><a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>К содержимому</a><aside className="sidebar"><a className="brand" href="#today" aria-label="Academy AI — главная"><span className="brand-mark"><GraduationCap size={23} /></span><span>academy<span className="brand-ai">ai</span></span></a><span className="sidebar-label">ТВОЁ ПРОСТРАНСТВО</span><nav aria-label="Основная навигация">{sections.map(item => <a key={item.id} href={`#${item.id}`} className={section === item.id ? 'active' : ''} aria-current={section === item.id ? 'page' : undefined}><item.icon size={21} /><span>{item.label}</span>{section === item.id && <span className="nav-dot" />}</a>)}</nav><div className="sidebar-bottom"><div className="sidebar-quote"><Leaf size={23} /><p>Не спеши.<br />Просто продолжай.</p></div><div className="profile"><span>Я</span><div><strong>Моё обучение</strong><small>Личное пространство</small></div></div></div></aside>
    <ReminderHost /><div className="workspace"><header className="topbar"><div className="breadcrumbs">Моё пространство<ChevronRight size={14} /><strong>{route === 'settings' ? 'Настройки' : route === 'vocabulary' ? 'Словарь' : lessonSlug ? 'Урок' : sections.find(s => s.id === section)?.label}</strong></div><div className="topbar-actions"><button className="theme-button" aria-label="Настройки" onClick={() => navigate('settings')}><Settings2 size={19} /></button><span className="xp-pill"><Zap size={16} />{progress?.total_xp ?? '—'} XP</span><button className="theme-button" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}>{theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}</button><span className="avatar">Я</span></div></header>
      <main id="main-content" tabIndex={-1}><div className="page-heading"><div><p className="date-label">{today}</p><h1>{route === 'settings' ? 'Твоё пространство' : lessonSlug ? 'Время для знаний' : titles[section ?? 'learn']}</h1></div><span className="local-badge"><span />Личное обучение</span></div>
        {error && <ErrorBox message={error} retry={refresh} />}
        {loading ? <Loading /> : route === 'settings' ? <Settings /> : route === 'vocabulary' ? <Vocabulary onSaved={refresh} /> : lessonSlug ? <LessonPlayer key={lessonSlug} slug={lessonSlug} onSaved={refresh} onExit={() => navigate('learn')} catalogue={lessons} /> : progress ? section === 'today' ? <Today lessons={lessons} progress={progress} onSaved={refresh} /> : section === 'learn' ? <Curriculum lessons={lessons} progress={progress} /> : section === 'plan' ? <Planner onSaved={refresh} /> : <Analytics lessons={lessons} progress={progress} /> : null}
        <footer><span>Academy AI</span><span>Твоё пространство для роста <Leaf size={13} /></span></footer>
      </main>
    </div>
  </div>
}
