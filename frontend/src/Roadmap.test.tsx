import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import Roadmap from './Roadmap'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
test('target settings persist without inventing monthly milestones before selection',async()=>{
  const prefs={available_minutes:[90,90,90,90,90,180,180],daily_goal_minutes:30,weekly_goal_minutes:210,reminder_enabled:false,reminder_time:'19:00',timezone:'Asia/Almaty',english_percent:65,monthly_goal_minutes:900,target_month:null}
  const roadmap={today:'2026-11-04',target_month:null,english_percent:65,monthly_goal:{target_minutes:900,completed_minutes:0,reached:false},months:[],topics:[],recommendations:[],ielts:[],mastered_count:0,total_topics:40,notice:'Охват тем, не балл IELTS.'}
  const fetch=vi.fn(async(url:string,options?:RequestInit)=>{if(options?.body)Object.assign(prefs,JSON.parse(options.body as string));return{ok:true,json:async()=>structuredClone(url.endsWith('/roadmap')?roadmap:prefs)}})
  vi.stubGlobal('fetch',fetch)
  render(<Roadmap onSaved={vi.fn()}/>)
  expect(await screen.findByRole('heading',{name:'Начни с месяца'})).toBeVisible()
  const user=userEvent.setup()
  const ratio=screen.getByRole('spinbutton',{name:'Доля английского, %'})
  await user.clear(ratio);await user.type(ratio,'80')
  await user.click(screen.getByRole('button',{name:'Сохранить цель'}))
  expect(await screen.findByText(/Цель сохранена/)).toBeVisible()
  const body=JSON.parse(fetch.mock.calls.find(([,options])=>options?.body)![1]!.body as string)
  expect(body.english_percent).toBe(80)
  expect(body).not.toHaveProperty('timezone')
  expect(screen.getByRole('progressbar',{name:'Цель месяца'})).toHaveAttribute('aria-valuenow','0')
})
