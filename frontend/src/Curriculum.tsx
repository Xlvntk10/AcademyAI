import { useState } from 'react'
import { ArrowRight, BookOpen, CheckCircle2, Clock3, Code2, Search } from 'lucide-react'
import type { Lesson, Progress } from './api'

export default function Curriculum({ lessons, progress }: { lessons: Lesson[]; progress: Progress }) {
  const [subject, setSubject] = useState<'english' | 'python'>('english')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const catalogue = lessons.filter(l => l.subject === subject).sort((a,b) => a.position-b.position)
  const completed = catalogue.filter(l => progress.lessons.find(p => p.slug === l.slug)?.completed_runs).length
  const visible = catalogue.filter(l => {
    const stats = progress.lessons.find(p => p.slug === l.slug)
    return `${l.title} ${l.topic} ${l.summary}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'completed' ? !!stats?.completed_runs : !stats?.completed_runs))
  })
  return <><div className="page-intro"><p>Твоя библиотека</p><h2>Знания, которые остаются.</h2><span>Понятная теория, практика и объяснение каждого ответа.</span></div>
    <div className="academy-tabs" role="tablist" aria-label="Направление обучения"><button role="tab" aria-selected={subject === 'english'} className={subject === 'english' ? 'selected' : ''} onClick={() => setSubject('english')}><BookOpen size={19} /><span>English Academy<small>Английский A2</small></span></button><button role="tab" aria-selected={subject === 'python'} className={subject === 'python' ? 'selected' : ''} onClick={() => setSubject('python')}><Code2 size={19} /><span>Code Academy<small>Python с самого начала</small></span></button></div>
    <section className={`academy-banner ${subject}`}><div><span className="eyebrow">{subject === 'english' ? 'ОСНОВА ДЛЯ БУДУЩЕГО IELTS' : 'ПЕРВЫЕ ШАГИ В COMPUTER SCIENCE'}</span><h3>{subject === 'english' ? 'Понимать. Говорить. Двигаться дальше.' : 'Понимай код, шаг за шагом.'}</h3><p>{subject === 'english' ? 'Грамматика и словарь A2, тексты об учёбе и технологиях. Без обещаний экзаменационного балла.' : 'Переменные, условия, циклы и структуры данных. Объективные задания без запуска пользовательского кода.'}</p></div><div className="course-completion"><strong>{completed}<small>/{catalogue.length}</small></strong><span>уроков завершено</span></div></section>
    <div className="catalogue-toolbar"><label className="search-input"><Search size={17} /><input aria-label="Найти урок" placeholder="Найти тему или урок…" value={query} onChange={e => setQuery(e.target.value)} /></label><select aria-label="Фильтр уроков" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Все уроки</option><option value="new">Ещё не завершены</option><option value="completed">Завершены</option></select></div>
    <div className="curriculum-grid">{visible.map(lesson => { const stats = progress.lessons.find(s => s.slug === lesson.slug); return <article className="curriculum-card" key={lesson.slug}><div className="curriculum-top"><span className={`lesson-number ${subject}`}>{String(lesson.position).padStart(2,'0')}</span><span className="small-note">{lesson.topic}</span>{!!stats?.completed_runs && <CheckCircle2 size={19} className="green" />}</div><h3>{lesson.title}</h3><p>{lesson.summary}</p><div className="metadata"><span><Clock3 size={14} />{lesson.duration_minutes} мин</span><span><BookOpen size={14} />{lesson.exercise_count} заданий</span><span>{lesson.level}</span></div><div className="card-bottom"><span className="small-note">{stats?.completed_runs ? `Лучший: ${stats.best_score}/${stats.max_score}` : stats?.active_run_id ? 'Урок начат' : `До ${lesson.max_score} XP`}</span><a className="primary compact" href={`#lesson/${lesson.slug}`}>{stats?.active_run_id ? 'Продолжить' : stats?.completed_runs ? 'Повторить' : 'Начать'}<ArrowRight size={15} /></a></div></article> })}</div>
    {!visible.length && <div className="panel empty-state"><Search size={28} /><h3>Ничего не найдено</h3><p>Попробуй другой запрос или выбери «Все уроки».</p><button className="secondary" onClick={() => { setQuery(''); setFilter('all') }}>Сбросить фильтры</button></div>}
  </>
}
