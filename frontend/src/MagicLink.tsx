import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { remember } from './Account'
import type { AccountSession } from './account-context'

export type LinkCallback = { code?: string; error?: string }
const invalidLink = 'Ссылка устарела или не подходит для этого входа. Запроси новое письмо в Academy AI и открой его в этом же браузере.'

// Run once before mounting React, so StrictMode cannot consume the URL twice.
// Keep the short-lived code only in memory; never put it into browser storage.
export function readLinkCallback(): LinkCallback | null {
  const url = new URL(window.location.href)
  const fragment = new URLSearchParams(url.hash.slice(1))
  const authKeys = ['code', 'error', 'error_code', 'error_description', 'access_token', 'refresh_token', 'token_hash']
  const present = authKeys.some(key => url.searchParams.has(key) || fragment.has(key))
  if (url.pathname !== '/auth/callback' && !present) return null
  window.history.replaceState(null, '', '/auth/callback')
  // Legacy implicit-token links are deliberately rejected; no token import endpoint.
  if (fragment.size || url.searchParams.has('error') || url.searchParams.has('error_code') ||
      url.searchParams.has('access_token') || url.searchParams.has('refresh_token') || url.searchParams.has('token_hash')) {
    return {error: invalidLink}
  }
  const codes = url.searchParams.getAll('code')
  if (codes.length !== 1 || !/^[A-Za-z0-9_-]{1,2048}$/.test(codes[0])) return {error: invalidLink}
  return {code: codes[0]}
}

export function MagicLinkCallback({callback, onSuccess = () => window.location.replace('/#account')}: {
  callback: LinkCallback; onSuccess?: () => void
}) {
  const started = useRef(false)
  const inFlight = useRef(false)
  const [busy, setBusy] = useState(Boolean(callback.code))
  const [notice, setNotice] = useState(callback.error || '')
  async function complete() {
    if (!callback.code || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setNotice('')
    try {
      const session = await api<AccountSession>('/auth/exchange', {code: callback.code})
      if (session.mode !== 'supabase' || !session.user) throw new Error('Сервер не подтвердил вход. Запроси новое письмо.')
      remember(session)
      onSuccess()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Не удалось подтвердить вход. Запроси новое письмо.')
    } finally { inFlight.current = false; setBusy(false) }
  }
  useEffect(() => {
    if (started.current) return
    started.current = true
    void complete()
    // This component owns one captured callback; never re-exchange on render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return <main className="account-entry"><section className="panel settings-panel">
    <h1>Academy AI</h1><h2>Вход по ссылке</h2>
    <p role="status">{busy ? 'Подтверждаем вход и открываем твой профиль…' : notice || 'Вход подтверждён.'}</p>
    {!busy && notice && <><p>Открой последнее письмо в том же браузере, где ты запросил ссылку. Старые ссылки и ссылки с другого устройства не подойдут. Сохранённые уроки и ответы остаются на месте.</p>
      <div className="button-row">{callback.code && <button className="secondary" onClick={() => void complete()}>Повторить подключение</button>}<a className="primary" href="/">Запросить новое письмо</a></div></>}
  </section></main>
}
