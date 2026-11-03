import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import Vocabulary from './Vocabulary'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
test('words stay optional and a server-reviewed word keeps its next date after remount', async () => {
  const word = {id:1,term:'usually',translation:'обычно',example:'I usually read.',lesson_slug:'a2-daily-routine',unlocked:true,added:false,due_on:null as string|null,box:0,review_count:0,correct_count:0}
  const data = {today:'2026-11-04',words:[word],due_count:0,added_count:0}
  let reviewBody: Record<string, unknown> = {}
  vi.stubGlobal('fetch', vi.fn(async (url:string, options?:RequestInit) => {
    let result:unknown = data
    if (url.endsWith('/add')) { Object.assign(word,{added:true,due_on:data.today}); data.added_count=1; data.due_count=1 }
    if (url.endsWith('/review')) {
      reviewBody=JSON.parse(options!.body as string)
      result={id:reviewBody.request_id,card_id:1,answer:reviewBody.answer,is_correct:false,correct_answer:'usually',example:word.example,due_on:'2026-11-05',box:0}
      Object.assign(word,{due_on:'2026-11-05',review_count:1}); data.due_count=0
    }
    return {ok:true,json:async()=>structuredClone(result)}
  }))
  const user = userEvent.setup()
  const saved = vi.fn()
  const view = render(<Vocabulary onSaved={saved} />)
  await user.click(await screen.findByRole('button',{name:'Добавить на повторение'}))
  await user.click(await screen.findByRole('button',{name:/Повторить слова/}))
  await user.type(screen.getByRole('textbox'), 'often')
  await user.click(screen.getByRole('button',{name:'Проверить'}))
  expect(await screen.findByRole('status')).toHaveTextContent('Запомним и вернёмся завтра')
  expect(reviewBody).toEqual({request_id:expect.any(String),answer:'often'})
  expect(saved).toHaveBeenCalledOnce()
  view.unmount()
  render(<Vocabulary onSaved={saved} />)
  expect(await screen.findByText(/Повторить 5 нояб/)).toBeVisible()
  expect(screen.queryByRole('button',{name:/Повторить слова/})).not.toBeInTheDocument()
})
