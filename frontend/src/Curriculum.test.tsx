import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, test, expect } from 'vitest'
import Curriculum from './Curriculum'
import type { Lesson } from './api'

afterEach(cleanup)
test('subject tabs and search show real lessons without fabricated progress', async () => {
  const base = { id:1, duration_minutes:20, exercise_count:6, max_score:60, version:1, position:1 }
  const lessons: Lesson[] = [{ ...base, slug:'english', title:'Everyday facts', subject:'english', topic:'Present Simple', summary:'Привычки', level:'A2' },{ ...base,id:2,slug:'python',title:'Переменные',subject:'python',topic:'Переменные',summary:'Имена для данных',level:'Beginner' }]
  render(<Curriculum lessons={lessons} progress={{ completed_lessons:0, completed_runs:0,total_xp:0,lessons:[] }} />)
  expect(screen.getByRole('heading',{name:'Everyday facts'})).toBeVisible()
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab',{name:/Code Academy/}))
  expect(screen.getByRole('heading',{name:'Переменные'})).toBeVisible()
  expect(screen.queryByRole('heading',{name:'Everyday facts'})).not.toBeInTheDocument()
  await user.type(screen.getByRole('textbox',{name:'Найти урок'}),'missing')
  expect(screen.getByRole('heading',{name:'Ничего не найдено'})).toBeVisible()
  await user.click(screen.getByRole('button',{name:'Сбросить фильтры'}))
  expect(screen.getByRole('link',{name:'Начать'})).toHaveAttribute('href','#lesson/python')
})
