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
