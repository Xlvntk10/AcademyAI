import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, Clock3 } from 'lucide-react'
import { api, newRequestId } from './api'
import { dateLabel, message } from './Planner'

type Word = { id: number; term: string; translation: string; example: string; lesson_slug: string; unlocked: boolean; added: boolean; due_on: string | null; box: number; review_count: number; correct_count: number }
type Dictionary = { today: string; words: Word[]; due_count: number; added_count: number }
type Review = { id: string; card_id: number; answer: string; is_correct: boolean; correct_answer: string; example: string; due_on: string; box: number }

export default function Vocabulary({ onSaved }: { onSaved: () => void }) {
  const [data, setData] = useState<Dictionary | null>(null)
  const [active, setActive] = useState<Word | null>(null)
  const [answer, setAnswer] = useState('')
  const [feedback, setFeedback] = useState<Review | null>(null)
  const [requestId, setRequestId] = useState(newRequestId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => { try { setData(await api<Dictionary>('/vocabulary')); setError('') } catch (e) { setError(message(e)) } }, [])
  useEffect(() => { void load() }, [load])
  async function add(word: Word) {
    setBusy(true); setError('')
    try { setData(await api<Dictionary>(`/vocabulary/${word.id}/add`)) }
    catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  function next() {
    const word = data?.words.find(w => w.added && w.due_on! <= data.today) ?? null
    setActive(word); setAnswer(''); setFeedback(null); setRequestId(newRequestId()); setError('')
  }
  async function submit() {
    if (!active || !answer.trim()) return
    setBusy(true); setError('')
    try {
      const result = await api<Review>(`/vocabulary/${active.id}/review`, { request_id: requestId, answer })
      setFeedback(result)
      setData(current => current && ({ ...current, due_count: Math.max(0, current.due_count - 1), words: current.words.map(w => w.id === active.id ? { ...w, due_on: result.due_on, box: result.box, review_count: w.review_count + 1, correct_count: w.correct_count + Number(result.is_correct) } : w) }))
      onSaved()
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <><a className="text-button" href="#learn"><ArrowLeft size={17} />К обучению</a><div className="page-intro"><p>Слова, которые остаются</p><h2>Немного повторения — каждый день.</h2><span>После урока добавь его слова. Сервер назначит следующую дату по твоим ответам.</span></div>
    {error && <div className="error-box" role="alert">{error}<button className="text-button" onClick={() => { setActive(null); void load() }}>Обновить словарь</button></div>}
    {!data ? <div className="loading" role="status">Загружаем словарь…</div> : active ? <section className="panel vocabulary-practice"><span className="eyebrow green">ВСПОМНИ СЛОВО ПО-АНГЛИЙСКИ</span><h3>{active.translation}</h3><form onSubmit={event => { event.preventDefault(); if (feedback) next(); else void submit() }}><label className="text-answer">Твой ответ<input autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={100} required value={answer} onChange={event => setAnswer(event.target.value)} disabled={busy || !!feedback} /></label>
      {feedback && <div className={`feedback ${feedback.is_correct ? 'correct' : 'incorrect'}`} role="status"><strong>{feedback.is_correct ? 'Верно!' : 'Запомним и вернёмся завтра'}</strong><p>{feedback.correct_answer} — {active.translation}</p><p>{feedback.example}</p><small><CheckCircle2 size={14} />Сохранено. Следующее повторение: {dateLabel(feedback.due_on)}</small></div>}
      <div className="exercise-actions"><button type="button" className="text-button" disabled={busy} onClick={() => setActive(null)}>К словарю</button><button className="primary" disabled={busy || (!feedback && !answer.trim())}>{busy ? 'Сохраняем…' : feedback ? data.due_count ? 'Следующее слово' : 'Готово на сегодня' : 'Проверить'}<ArrowRight size={16} /></button></div></form></section> : <>
      <section className="panel vocabulary-summary"><BookOpen className="green" size={27} /><div><h3>На повторении: {data.added_count} из {data.words.length}</h3><p className="small-note">Сегодня ждут: {data.due_count}. Успешные ответы увеличивают интервал: 1, 3, 7, 14, 30 дней. Ошибка возвращает слово на завтра.</p></div>{data.due_count > 0 && <button className="primary compact" onClick={next}>Повторить слова<ArrowRight size={16} /></button>}</section>
      <p className="small-note vocabulary-note">Добавление слов — твой выбор. Повторение поддерживает streak, но не добавляет XP. Время учитывай отдельной отметкой в плане.</p>
      <div className="vocabulary-grid">{data.words.map(word => <article className="panel word-card" key={word.id}><div className="section-heading"><h3 lang="en">{word.term}</h3>{word.added && <Clock3 className="green" size={17} />}</div><p>{word.translation}</p><blockquote lang="en">{word.example}</blockquote>{word.added ? <><span className="small-note">{word.due_on! <= data.today ? 'Пора повторить' : `Повторить ${dateLabel(word.due_on!)}`} · этап {word.box}/5</span><span className="small-note">Верно {word.correct_count} из {word.review_count} повторений</span></> : word.unlocked ? <button className="secondary compact" disabled={busy} onClick={() => add(word)}>Добавить на повторение</button> : <a className="text-button" href={`#lesson/${word.lesson_slug}`}>Сначала пройди урок<ArrowRight size={14} /></a>}</article>)}</div>
    </>}
  </>
}
