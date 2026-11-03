import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import Ielts from './Ielts'
import { ListeningAudio, SpeakingRecorder } from './ielts-media'

afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear()})
test('writing draft is saved, restored and submitted without a fabricated band',async()=>{
  let run={id:'draft-1',test_id:'writing-task1',title:'Task 1',section:'writing',started_at:new Date().toISOString(),updated_at:new Date().toISOString(),submitted_at:null as string|null,revision:0,answers:{},text:'',mode:'text',result:null as any}
  const task={id:'writing-task1',title:'Task 1',section:'writing',instructions:'Practice only',duration_seconds:1200,content:{introduction:'Original task',prompt:'Describe the table.',min_words:150,criteria:[]}}
  const fetch=vi.fn(async(url:string,options?:RequestInit)=>{
    if(options?.body){const body=JSON.parse(options.body as string);run={...run,...body,revision:run.revision+1};if(url.endsWith('/submit'))run={...run,submitted_at:new Date().toISOString(),result:{score:null,word_count:2,elapsed_seconds:5,over_time:false,notice:'Учебная практика.',recommendations:['Добавь сравнения.']}}}
    return {ok:true,json:async()=>structuredClone(url.includes('/tests/')?task:run)}
  })
  vi.stubGlobal('fetch',fetch)
  const user=userEvent.setup()
  const view=render(<Ielts route="ielts/run/draft-1" onSaved={vi.fn()}/>)
  await user.type(await screen.findByRole('textbox'),'English increased.')
  await user.click(screen.getByRole('button',{name:'Сохранить черновик'}))
  expect(await screen.findByText('Черновик сохранён на сервере.')).toBeVisible()
  view.unmount()
  render(<Ielts route="ielts/run/draft-1" onSaved={vi.fn()}/>)
  expect(await screen.findByRole('textbox')).toHaveValue('English increased.')
  await user.click(screen.getByRole('button',{name:/Завершить тренировку/}))
  expect(await screen.findByText(/Числовая оценка не выставляется/)).toBeVisible()
  expect(screen.getByText('Добавь сравнения.')).toBeVisible()
  const body=JSON.parse(fetch.mock.calls.find(([url])=>url.endsWith('/submit'))![1]!.body as string)
  expect(body).not.toHaveProperty('score')
})
test('Listening never selects a remote voice and offers a labelled text fallback',async()=>{
  const speak=vi.fn()
  vi.stubGlobal('speechSynthesis',{getVoices:()=>[{localService:false,lang:'en-US'}],addEventListener:vi.fn(),removeEventListener:vi.fn(),cancel:vi.fn(),speak})
  const onMode=vi.fn()
  render(<ListeningAudio transcript="A fictional conversation." onMode={onMode}/>)
  expect(screen.getByRole('button',{name:'Слушать'})).toBeDisabled()
  await userEvent.setup().click(screen.getByRole('button',{name:'Открыть текст'}))
  expect(screen.getByText('A fictional conversation.')).toBeVisible()
  expect(onMode).toHaveBeenCalledWith('text')
  expect(speak).not.toHaveBeenCalled()
})
test('Speaking explains unavailable recording without requesting a microphone',()=>{
  vi.stubGlobal('isSecureContext',false)
  render(<SpeakingRecorder id="test" disabled={false} onMode={vi.fn()} onRecording={vi.fn()}/>)
  expect(screen.getByText(/Запись недоступна/)).toBeVisible()
  expect(screen.queryByRole('button',{name:'Записать голос'})).not.toBeInTheDocument()
})

test('stale local writing is offered for recovery instead of being silently overwritten',async()=>{
  const saved={id:'conflict-1',test_id:'writing-task2',title:'Task 2',section:'writing',started_at:new Date().toISOString(),updated_at:new Date().toISOString(),submitted_at:null,revision:2,answers:{},text:'Server version.',mode:'text',result:null}
  const task={id:'writing-task2',title:'Task 2',section:'writing',instructions:'Practice',duration_seconds:2400,content:{introduction:'Original prompt',prompt:'Discuss both views.'}}
  localStorage.setItem('academy-ielts-draft-conflict-1',JSON.stringify({revision:1,answers:{},text:'My unsaved paragraph.',mode:'text'}))
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>structuredClone(url.includes('/tests/')?task:saved)})))
  render(<Ielts route="ielts/run/conflict-1" onSaved={vi.fn()}/>)
  expect(await screen.findByRole('textbox',{name:'Локальная несохранённая копия'})).toHaveValue('My unsaved paragraph.')
  expect(screen.getByRole('button',{name:'Сохранить черновик'})).toBeDisabled()
  expect(Object.keys(localStorage).some(key=>key.startsWith('academy-ielts-draft-conflict-1-conflict-'))).toBe(true)
  await userEvent.setup().click(screen.getByRole('button',{name:'Восстановить локальную версию'}))
  expect(screen.getByRole('textbox',{name:'Твоя работа'})).toHaveValue('My unsaved paragraph.')
})

test('microphone denied keeps text mode available and releases the recording lock',async()=>{
  const descriptor=Object.getOwnPropertyDescriptor(navigator,'mediaDevices')
  const getUserMedia=vi.fn(async()=>{throw new Error('Permission denied')})
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia}})
  vi.stubGlobal('isSecureContext',true)
  vi.stubGlobal('MediaRecorder',class {})
  const lock=vi.fn()
  try {
    render(<SpeakingRecorder id="denied" disabled={false} onMode={vi.fn()} onRecording={lock}/>)
    expect(getUserMedia).not.toHaveBeenCalled()
    await userEvent.setup().click(screen.getByRole('button',{name:'Записать голос'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Напиши ответ в текстовом поле')
    expect(lock).toHaveBeenLastCalledWith(false)
    expect(getUserMedia).toHaveBeenCalledWith({audio:true})
  } finally {
    if(descriptor)Object.defineProperty(navigator,'mediaDevices',descriptor)
    else delete (navigator as any).mediaDevices
  }
})

test('a local English voice with a short language tag is supported',async()=>{
  const voice={localService:true,lang:'en',name:'Local English'}
  const speak=vi.fn()
  vi.stubGlobal('speechSynthesis',{getVoices:()=>[voice],addEventListener:vi.fn(),removeEventListener:vi.fn(),cancel:vi.fn(),speak})
  vi.stubGlobal('SpeechSynthesisUtterance',class {text:string;constructor(text:string){this.text=text}})
  const mode=vi.fn()
  render(<ListeningAudio transcript="Original practice audio." onMode={mode}/>)
  await userEvent.setup().click(screen.getByRole('button',{name:'Слушать'}))
  expect(speak.mock.calls[0][0].voice).toBe(voice)
  expect(mode).toHaveBeenCalledWith('audio')
})
