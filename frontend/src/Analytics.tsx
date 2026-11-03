import { useEffect, useState } from 'react'
import { ArrowRight, Award, Check, Flame, Target, Trophy, Zap } from 'lucide-react'
import { api, type Progress, type Lesson } from './api'
import { dateLabel, message } from './Planner'

type Activity = { date: string; answers: number; correct_answers: number; completed_runs: number; tasks: number; minutes: number; practice_xp: number }
type Goal = { target_minutes: number; completed_minutes: number; reached: boolean }
export type Dashboard = {
  today: string; timezone: string; total_xp: number; lesson_xp: number; practice_xp: number; level: number; level_title: string; xp_in_level: number; xp_to_next_level: number
  current_streak: number; longest_streak: number; completed_lessons: number; completed_runs: number; answers: number; correct_answers: number; accuracy: number | null; minutes: number
  daily_goal: Goal; weekly_goal: Goal; activity: Activity[]
  subjects: { subject: string; completed_lessons: number; available_lessons: number; answers: number; correct_answers: number; accuracy: number | null; minutes: number; lesson_xp: number }[]
  achievements: { code: string; title: string; description: string; target: number; progress: number; unlocked_on: string | null; reward: string }[]
  weekly_report: { start: string; end: string; active_days: number; minutes: number; completed_runs: number; answers: number; correct_answers: number; accuracy: number | null; english_minutes: number; python_minutes: number }
}

function useDashboard(refreshKey: unknown) {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => { let live = true; api<Dashboard>('/dashboard').then(result => { if (live) { setData(result); setError('') } }).catch(e => { if (live) setError(message(e)) }); return () => { live = false } }, [refreshKey, retry])
  return { data, error, retry: () => setRetry(n => n + 1) }
}

function Meter({ goal, label }: { goal: Goal; label: string }) {
  return <div className="goal-meter"><div><span>{label}</span><strong>{goal.completed_minutes} / {goal.target_minutes} мин {goal.reached && <Check size={14} />}</strong></div><div className="progress-track" role="progressbar" aria-label={label} aria-valuenow={Math.min(goal.completed_minutes, goal.target_minutes)} aria-valuemin={0} aria-valuemax={goal.target_minutes}><span style={{ width: `${Math.min(100, goal.completed_minutes / goal.target_minutes * 100)}%` }} /></div></div>
}

export function Motivation({ progress }: { progress: Progress }) {
  const { data, error, retry } = useDashboard(progress)
  if (error) return <div className="panel small-note" role="alert">{error}<button className="text-button" onClick={retry}>Повторить</button></div>
  if (!data) return <div className="panel small-note" role="status">Загружаем цели…</div>
  return <section className="panel motivation-panel"><div className="section-heading"><h3>Твой ритм</h3><Flame size={20} className="flame" /></div><div className="rhythm-numbers"><strong>{data.current_streak}<small>дней подряд</small></strong><strong>{data.level}<small>уровень</small></strong></div><Meter goal={data.daily_goal} label="Сегодня" /><Meter goal={data.weekly_goal} label="За неделю" /><p className="small-note">Минуты из выполненных заданий плана.</p><a className="text-button" href="#progress">Все результаты<ArrowRight size={15} /></a></section>
}

function WeekChart({ days }: { days: Activity[] }) {
  const max = Math.max(30, ...days.map(d => d.minutes))
  return <svg className="activity-chart" viewBox="0 0 560 170" role="img" aria-label={`Минуты занятий за последние семь дней: ${days.map(d => `${dateLabel(d.date)} — ${d.minutes}`).join('; ')}`}>
    <line x1="20" y1="133" x2="540" y2="133" stroke="var(--border)" />
    {days.map((day, i) => { const height = day.minutes / max * 95; return <g key={day.date}><rect x={30+i*75} y={133-height} width="39" height={height} rx="5" fill="var(--green)" opacity=".8"><title>{dateLabel(day.date)}: {day.minutes} мин</title></rect><text x={49+i*75} y={Math.max(20,123-height)} textAnchor="middle" fill="var(--text)" fontSize="12">{day.minutes}</text><text x={49+i*75} y="157" textAnchor="middle" fill="var(--muted)" fontSize="10">{dateLabel(day.date)}</text></g> })}
  </svg>
}

export default function Analytics({ progress, lessons }: { progress: Progress; lessons: Lesson[] }) {
  const { data, error, retry } = useDashboard(progress)
  if (error) return <div className="error-box" role="alert">{error}<button className="text-button" onClick={retry}>Повторить</button></div>
  if (!data) return <div className="loading" role="status">Собираем твои результаты…</div>
  const report = data.weekly_report
  const completed = progress.lessons.filter(s => s.last_result)
  return <><div className="page-intro"><p>Твои результаты</p><h2>{data.answers || data.minutes ? 'Твои усилия становятся знаниями.' : 'Здесь начинается твоя история.'}</h2><span>Только сохранённые ответы и отмеченные тобой занятия.</span></div>
    <div className="analytics-stats"><div className="stat-card"><span className="stat-icon yellow"><Zap size={20} /></span><strong>{data.total_xp}<small>XP</small></strong><span>Всего опыта</span></div><div className="stat-card"><span className="stat-icon green-bg"><Award size={20} /></span><strong>{data.level}</strong><span>{data.level_title}</span></div><div className="stat-card"><span className="stat-icon yellow"><Flame size={20} /></span><strong>{data.current_streak}</strong><span>Дней подряд · рекорд {data.longest_streak}</span></div><div className="stat-card"><span className="stat-icon lilac"><Target size={20} /></span><strong>{data.accuracy === null ? '—' : `${data.accuracy}%`}</strong><span>Верно {data.correct_answers} из {data.answers}</span></div></div>
    <div className="level-strip"><span>Уровень {data.level}</span><div className="progress-track"><span style={{ width: `${data.xp_in_level}%` }} /></div><span>До следующего: {data.xp_to_next_level} XP</span></div>
    <p className="small-note">Уроки: {data.lesson_xp} XP за лучшие результаты. Самостоятельная практика: {data.practice_xp} XP, максимум 10 за направление в день. Уровень — игровой показатель, не оценка IELTS.</p>
    <div className="analytics-columns"><section className="panel"><div className="section-heading"><h3>Твои цели</h3><Target size={18} className="green" /></div><Meter goal={data.daily_goal} label="Ежедневная цель" /><Meter goal={data.weekly_goal} label="Еженедельная цель" /><p className="small-note">Всего подтверждено {data.minutes} мин. Отмечай фактическое время в плане.</p><a className="text-button" href="#plan">Изменить цели<ArrowRight size={15} /></a></section><section className="panel"><h3>Активность за 7 дней</h3><WeekChart days={data.activity.slice(-7)} /><p className="small-note">Минуты по твоим отметкам. Нулевой столбец означает, что время не отмечено.</p></section></div>
    <div className="section-heading"><h2>Твои направления</h2><span className="small-note">{data.completed_lessons} уроков · {data.completed_runs} прохождений</span></div><div className="subject-stats">{data.subjects.map(subject => <section className="panel" key={subject.subject}><span className={`subject-label ${subject.subject}`}>{subject.subject === 'english' ? 'English Academy' : 'Code Academy'}</span><h3>{subject.completed_lessons} / {subject.available_lessons} уроков</h3><div className="metadata"><span>{subject.correct_answers} / {subject.answers} верных ответов</span><span>{subject.accuracy === null ? 'Точность пока неизвестна' : `${subject.accuracy}% точности`}</span><span>{subject.minutes} мин практики</span></div><p className="small-note">{subject.answers ? 'Повторение учитывается в точности ответов.' : 'Пройди первое упражнение, чтобы увидеть результат.'}</p></section>)}</div>
    <div className="section-heading"><h2>Календарь активности</h2><span className="small-note">12 недель · Asia/Almaty</span></div><section className="panel"><div className="heatmap" role="list" aria-label="Календарь активности">{data.activity.map(day => { const events = day.answers + day.tasks; return <div key={day.date} role="listitem" tabIndex={0} title={`${dateLabel(day.date)}: ${day.answers} ответов, ${day.tasks} заданий, ${day.minutes} мин`} aria-label={`${day.date}: ${day.answers} ответов, ${day.tasks} заданий, ${day.minutes} минут`} className={`heat-cell heat-${events === 0 ? 0 : events < 3 ? 1 : events < 7 ? 2 : 3}`} /> })}</div><div className="heat-legend"><span>{dateLabel(data.activity[0].date)} — {dateLabel(data.today)}</span><span>Меньше <i className="heat-cell heat-0" /><i className="heat-cell heat-1" /><i className="heat-cell heat-2" /><i className="heat-cell heat-3" /> Больше</span></div><p className="small-note">День засчитывается в streak после сохранённого ответа или выполненного задания. Сегодняшний день можно завершить до полуночи.</p></section>
    <div className="section-heading"><h2>Достижения и награды</h2><span className="small-note">{data.achievements.filter(a => a.unlocked_on).length} из {data.achievements.length}</span></div><div className="achievement-grid">{data.achievements.map(item => <section className={`achievement panel ${item.unlocked_on ? 'unlocked' : ''}`} key={item.code}><span className="achievement-icon"><Trophy size={24} /></span><h3>{item.title}</h3><p>{item.description}</p><span className="small-note">{item.progress} / {item.target}{item.code === 'dedicated_student' ? ' мин' : ''}</span><div className="progress-track"><span style={{ width: `${item.progress/item.target*100}%` }} /></div>{item.unlocked_on ? <strong className="reward-label">{item.reward}<small>Получен {dateLabel(item.unlocked_on)}</small></strong> : <span className="small-note">Награда: {item.reward}</span>}</section>)}</div>
    <section className="panel weekly-report"><div className="section-heading"><h3>Отчёт за текущую неделю</h3><span className="small-note">{dateLabel(report.start)} — {dateLabel(report.end)}</span></div>{report.active_days ? <p>{report.active_days} активных дней, {report.completed_runs} завершённых прохождений и {report.correct_answers} верных ответов из {report.answers}. Отмечено {report.minutes} мин занятий: английский — {report.english_minutes}, Python — {report.python_minutes}.</p> : <p>За эту неделю ещё нет сохранённой активности. Начни с одного урока или задания плана.</p>}</section>
    <div className="section-heading"><h2>Последние результаты по урокам</h2></div>{completed.length ? <div className="results-list">{completed.map(s => <a className="result-row" key={s.slug} href={`#lesson/${s.slug}`}><span className="stat-icon green-bg"><Check size={22} /></span><span><strong>{lessons.find(l => l.slug === s.slug)?.title}</strong><small>Верно {s.last_result!.correct_count} из {s.last_result!.exercise_count} · лучший результат {s.best_score}/{s.max_score}</small></span><b>{s.last_result!.score}/{s.max_score}</b><ArrowRight size={18} /></a>)}</div> : <div className="panel empty-state"><BookEmpty /><h3>Первый результат впереди</h3><p>После завершения урока он появится здесь.</p><a className="primary" href="#learn">Выбрать урок<ArrowRight size={16} /></a></div>}
  </>
}

function BookEmpty() { return <Trophy size={34} /> }
