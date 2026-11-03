import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, Clock3, Headphones, Mic, PenLine } from 'lucide-react'
import { api, newRequestId } from './api'
import { message } from './Planner'
import { ListeningAudio, SpeakingRecorder } from './ielts-media'

type Section = 'listening' | 'reading' | 'writing' | 'speaking'
type Question = {id:string;prompt:string;options:string[]}
type Criterion = {title:string;description:string}
type Test = {id:string;section:Section;title:string;instructions:string;duration_seconds:number;content:{introduction:string;transcript?:string;passage?:string;questions?:Question[];prompt?:string;min_words?:number;preparation_seconds?:number;criteria?:Criterion[];guide?:string[];table?:{headers:string[];rows:string[][]}}}
type Result = {score:number|null;total?:number;percent?:number;word_count?:number;elapsed_seconds:number;over_time:boolean;notice:string;recommendations:string[];answers?:{id:string;prompt:string;answer:string;is_correct:boolean;correct_answer:string;explanation:string}[]}
type Run = {id:string;test_id:string;title:string;section:Section;started_at:string;updated_at:string;submitted_at:string|null;revision:number;answers:Record<string,string>;text:string;mode:'text'|'audio';result:Result|null}
const sections = [{id:'listening',title:'Listening',icon:Headphones},{id:'reading',title:'Reading',icon:BookOpen},{id:'writing',title:'Writing',icon:PenLine},{id:'speaking',title:'Speaking',icon:Mic}] as const
const go = (route:string) => { window.location.hash=route }
function Timer({start,seconds}: {start:string;seconds:number}) {
  const [now,setNow]=useState(Date.now())
  useEffect(()=>{const timer=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(timer)},[])
  const left=Math.max(0, seconds-Math.floor((now-new Date(start).getTime())/1000))
  return <span className="practice-timer"><Clock3 size={16}/>{Math.floor(left/60)}:{String(left%60).padStart(2,'0')}{!left && ' · время вышло, ответ можно сохранить'}</span>
}

function Practice({route,onSaved}:{route:string;onSaved:()=>void}) {
  const [test,setTest]=useState<Test|null>(null)
  const [run,setRun]=useState<Run|null>(null)
  const [text,setText]=useState('')
  const [answers,setAnswers]=useState<Record<string,string>>({})
  const [mode,setMode]=useState<'text'|'audio'>('text')
  const [recording,setRecording]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [preparation,setPreparation]=useState('')
  const [conflict,setConflict]=useState<{text:string;answers:Record<string,string>;mode:'text'|'audio'}|null>(null)
  const [requestId]=useState(newRequestId)
  const runId=route.startsWith('ielts/run/')?route.slice(10):null
  const load=useCallback(async()=>{
    try {
      if(runId){
        const saved=await api<Run>(`/ielts/runs/${runId}`)
        setRun(saved);setText(saved.text);setAnswers(saved.answers);setMode(saved.mode)
        try {
          const key=`academy-ielts-draft-${saved.id}`
          const draft=JSON.parse(localStorage.getItem(key)||'null')
          if(draft && typeof draft.text==='string' && draft.answers && ['text','audio'].includes(draft.mode)) {
            if(!saved.submitted_at && draft.revision===saved.revision){setText(draft.text);setAnswers(draft.answers);setMode(draft.mode)}
            else if(draft.text!==saved.text || JSON.stringify(draft.answers)!==JSON.stringify(saved.answers)) {
              setConflict(draft)
              localStorage.setItem(`${key}-conflict-${Date.now()}`,JSON.stringify(draft))
            }
          }
        } catch { /* Server draft is still available; an in-memory conflict is retained. */ }
        setTest(await api<Test>(`/ielts/tests/${saved.test_id}`))
      } else setTest(await api<Test>(`/ielts/tests/${route.slice(11)}`))
      setError('')
    }catch(e){setError(message(e))}
  },[route,runId])
  useEffect(()=>{void load()},[load])
  const dirty=!!run && !run.submitted_at && (run.text!==text || run.mode!==mode || JSON.stringify(run.answers)!==JSON.stringify(answers))
  useEffect(()=>{
    if(!run || conflict)return
    try{if(run.submitted_at)localStorage.removeItem(`academy-ielts-draft-${run.id}`);else localStorage.setItem(`academy-ielts-draft-${run.id}`,JSON.stringify({revision:run.revision,text,answers,mode}))}catch{setNotice('Локальное сохранение недоступно. Используй кнопку сохранения перед выходом.')}
  },[run,text,answers,mode,conflict])
  useEffect(()=>{if(!dirty)return; const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty])
  async function save(submit=false){
    if(!run)return
    setBusy(true);setError('')
    try{const saved=await api<Run>(`/ielts/runs/${run.id}/${submit?'submit':'save'}`,{revision:run.revision,answers,text,mode});setRun(saved);setNotice(submit?'Работа сохранена в истории.':'Черновик сохранён на сервере.');if(submit)onSaved()}
    catch(e){setError(message(e))}finally{setBusy(false)}
  }
  useEffect(()=>{if(!dirty||busy||error||conflict)return;const timer=window.setTimeout(()=>{void save()},2000);return()=>window.clearTimeout(timer)},[text,answers,mode,run,busy,error,dirty,conflict])
  async function start(){if(!test)return;setBusy(true);try{const value=await api<Run>(`/ielts/tests/${test.id}/runs`,{request_id:requestId});go(`ielts/run/${value.id}`)}catch(e){setError(message(e))}finally{setBusy(false)}}
  const changeMode=useCallback((value:'text'|'audio')=>setMode(value),[])
  if(!test)return <>{error?<div className="error-box" role="alert">{error}<button onClick={load}>Повторить</button></div>:<div className="loading" role="status">Открываем тренировку…</div>}</>
  const result=run?.result
  return <><a className="text-button" href="#ielts"><ArrowLeft size={16}/>К IELTS</a><div className="page-intro"><p>{test.section.toUpperCase()} · ТРЕНИРОВКА</p><h2>{test.title}</h2><span>{test.instructions}</span></div>
    <p className="small-note">{test.content.introduction}</p>{error&&<div className="error-box" role="alert">{error}</div>}{notice&&<p className="success-note" role="status">{notice}</p>}
    {conflict&&<section className="panel draft-conflict"><h3>Сохранены две разные версии</h3><p>Серверная работа обновилась после локальной копии. Скопируй нужный текст или выбери версию. Автосохранение приостановлено.</p><label className="essay-label">Локальная несохранённая копия<textarea readOnly value={conflict.text} rows={6}/></label>{Object.keys(conflict.answers).length>0&&<pre>{JSON.stringify(conflict.answers,null,2)}</pre>}<div className="button-row">{!run?.submitted_at&&<button className="secondary" onClick={()=>{setText(conflict.text);setAnswers(conflict.answers);setMode(conflict.mode);setConflict(null)}}>Восстановить локальную версию</button>}<button className="text-button" onClick={()=>setConflict(null)}>Оставить серверную версию</button></div></section>}
    {!run?<section className="panel practice-start"><div><h3>Спокойная практика с сохранением</h3><p>Ориентир: {Math.round(test.duration_seconds/60)} мин. Таймер идёт по часам и после обновления страницы; паузы не вычитаются. Это сокращённое задание, не полный экзамен.</p>{test.content.preparation_seconds&&<><p className="practice-passage" lang="en">{test.content.prompt}</p><button className="secondary compact" onClick={()=>setPreparation(new Date().toISOString())}>Минута подготовки</button>{preparation&&<Timer start={preparation} seconds={test.content.preparation_seconds}/>}</>}</div><button className="primary" disabled={busy} onClick={start}>Начать ответ<ArrowRight size={16}/></button></section>:<>
      {!run.submitted_at&&<div className="practice-toolbar"><Timer start={run.started_at} seconds={test.duration_seconds}/><span className="small-note">{busy?'Сохраняем…':dirty?'Есть несохранённые изменения':'Сохранено на сервере'}</span></div>}
      {test.content.transcript && !result&&<ListeningAudio transcript={test.content.transcript} onMode={changeMode}/> }
      {test.content.passage&&<section className="panel practice-passage" lang="en">{test.content.passage}</section>}
      {test.content.prompt&&<section className="panel practice-passage" lang="en">{test.content.prompt}</section>}
      {test.content.table&&<div className="table-scroll"><table className="practice-table"><caption>Original fictional dataset</caption><thead><tr>{test.content.table.headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{test.content.table.rows.map(row=><tr key={row[0]}>{row.map((cell,i)=><td key={i}>{cell}</td>)}</tr>)}</tbody></table></div>}
      {test.section==='speaking'&&<SpeakingRecorder id={run.id} disabled={!!run.submitted_at} onMode={changeMode} onRecording={setRecording}/>}
      {!result?<><div className="practice-questions">{test.content.questions?.map((q,i)=><fieldset className="panel practice-question" key={q.id} disabled={busy}><legend>{i+1}. {q.prompt}</legend>{q.options.length?q.options.map(option=><label className="practice-option" key={option}><input type="radio" name={q.id} checked={answers[q.id]===option} onChange={()=>{setAnswers({...answers,[q.id]:option});setError('')}}/>{option}</label>):<input aria-label={q.prompt} maxLength={500} value={answers[q.id]||''} onChange={e=>{setAnswers({...answers,[q.id]:e.target.value});setError('')}}/>}</fieldset>)}</div>
      {['writing','speaking'].includes(test.section)&&<section className="panel"><label className="essay-label">{test.section==='writing'?'Твоя работа':'Текстовый ответ или заметки к записи'}<textarea rows={15} maxLength={20000} value={text} disabled={busy} onChange={e=>{setText(e.target.value);setError('')}}/></label><p className="small-note">Примерный объём: {text.trim()?text.trim().split(/\s+/).length:0} слов{test.content.min_words?` · ориентир ${test.content.min_words}+`:''}. Окончательный счётчик вычисляет сервер.</p>{test.section==='speaking'&&<p className="small-note">Режим в истории: {mode==='audio'?'аудио (копия только в этом браузере)':'текст'}. По тексту нельзя проверить произношение.</p>}</section>}
      <div className="exercise-actions"><button className="secondary" disabled={busy || !!conflict} onClick={()=>save()}>Сохранить черновик</button><button className="primary" disabled={busy || recording || !!conflict} onClick={()=>save(true)}>Завершить тренировку<CheckCircle2 size={16}/></button></div></>:<section className="panel practice-result"><h3>Работа сохранена</h3><p>{result.notice}</p>{result.score!==null?<strong className="practice-score">{result.score}/{result.total} · {result.percent}%</strong>:<p>Числовая оценка не выставляется. Слов по счётчику: {result.word_count}.</p>}<p className="small-note">Режим: {run.mode==='audio'?'аудио':'текст'} · {Math.floor(result.elapsed_seconds/60)} мин {result.elapsed_seconds%60} с{result.over_time?' · ориентир времени превышен':''}</p>{run.text&&<details><summary>Мой сохранённый текст</summary><p className="practice-passage">{run.text}</p></details>}{result.recommendations.map(r=><p key={r}>{r}</p>)}{result.answers?.map(a=><details className="ielts-answer" key={a.id}><summary>{a.is_correct?'✓':'○'} {a.prompt}</summary><p>Твой ответ: {a.answer||'Не указан'}</p><p>Правильный ответ: {a.correct_answer}</p><p>{a.explanation}</p></details>)}{test.content.transcript&&<details><summary>Текст аудио</summary><p className="practice-passage" lang="en">{test.content.transcript}</p></details>}<a className="primary compact" href={`#ielts/test/${test.id}`}>Новая попытка<ArrowRight size={16}/></a></section>}
    </>}
    {!!test.content.criteria?.length&&<section className="criteria-grid">{test.content.criteria.map(c=><article className="panel" key={c.title}><h3>{c.title}</h3><p>{c.description}</p></article>)}</section>}
  </>
}

export default function Ielts({route,onSaved}:{route:string;onSaved:()=>void}) {
  const [tests,setTests]=useState<Test[]>([])
  const [history,setHistory]=useState<Run[]>([])
  const [section,setSection]=useState<Section>('listening')
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(true)
  const load=useCallback(async()=>{try{const [items,runs]=await Promise.all([api<Test[]>('/ielts/tests'),api<Run[]>('/ielts/history')]);setTests(items);setHistory(runs);setError('')}catch(e){setError(message(e))}finally{setLoading(false)}},[])
  useEffect(()=>{if(route==='ielts')void load()},[route,load])
  if(route!=='ielts')return <Practice key={route} route={route} onSaved={onSaved}/>
  return <><div className="page-intro"><p>IELTS · следующий горизонт</p><h2>Четыре навыка. Осознанная практика.</h2><span>Авторские сокращённые задания. Проценты здесь не переводятся в IELTS band score.</span></div><div className="ielts-tabs" role="tablist" aria-label="Навык IELTS">{sections.map(s=><button className={section===s.id?'selected':''} role="tab" aria-selected={section===s.id} key={s.id} onClick={()=>setSection(s.id)}><s.icon size={20}/>{s.title}</button>)}</div>{error&&<div className="error-box" role="alert">{error}<button onClick={load}>Повторить</button></div>}{loading?<p role="status">Загружаем тренировки…</p>:<div className="curriculum-grid">{tests.filter(t=>t.section===section).map(t=><article className="curriculum-card" key={t.id}><span className="eyebrow green">{t.section}</span><h3>{t.title}</h3><p>{t.instructions}</p><div className="card-bottom"><span className="small-note">Около {Math.round(t.duration_seconds/60)} мин</span><a className="primary compact" href={`#ielts/test/${t.id}`}>Открыть<ArrowRight size={16}/></a></div></article>)}</div>}<div className="section-heading"><h2>Мои работы</h2><span className="small-note">Последние 50</span></div>{history.length?<div className="results-list">{history.map(r=><a className="result-row" key={r.id} href={`#ielts/run/${r.id}`}><span><strong>{r.title}</strong><small>{new Date(r.started_at).toLocaleString('ru-RU',{timeZone:'Asia/Almaty'})} · {r.mode==='audio'?'Аудио':'Текст'}</small></span><b>{!r.submitted_at?'Черновик':r.result?.score!==null?`${r.result?.score}/${r.result?.total}`:'Сохранено'}</b><ArrowRight size={16}/></a>)}</div>:<div className="panel empty-state"><PenLine size={28}/><h3>Твоя первая работа впереди</h3><p>Черновики и завершённые тренировки появятся здесь после начала задания.</p></div>}</>
}
