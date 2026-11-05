import { useEffect, useState } from 'react'
import { checkPwaUpdate, waitingWorker } from './pwa'

export function UpdateNotice({ route }: { route: string }) {
  const [ready, setReady] = useState(() => !!waitingWorker())
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const update = () => setReady(!!waitingWorker())
    window.addEventListener('academy-update-ready', update)
    return () => window.removeEventListener('academy-update-ready', update)
  }, [])
  async function activate() {
    const worker = waitingWorker()
    if (!worker) return
    setBusy(true); setNotice('')
    const channel = new MessageChannel()
    const reload = () => window.location.reload()
    const timeout = window.setTimeout(() => {
      navigator.serviceWorker.removeEventListener('controllerchange', reload)
      channel.port1.close(); setBusy(false); setNotice('Обновление пока не завершилось. Закрой вкладки Academy AI и открой приложение заново.')
    }, 10000)
    navigator.serviceWorker.addEventListener('controllerchange', reload, { once: true })
    channel.port1.onmessage = event => {
      if (event.data.status === 'other-tabs') {
        clearTimeout(timeout); channel.port1.close(); setBusy(false)
        navigator.serviceWorker.removeEventListener('controllerchange', reload)
        setNotice('Закрой остальные вкладки Academy AI, затем повтори обновление.')
      }
    }
    worker.postMessage({ type: 'ACTIVATE_UPDATE' }, [channel.port2])
  }
  if (!ready) return route === 'settings' ? <button className="text-button" onClick={() => void checkPwaUpdate().then(() => setNotice('Проверка завершена. Доступное обновление появится здесь.')).catch(error => setNotice(error instanceof Error ? error.message : 'Для проверки обновлений нужно соединение с сервером.'))}>Проверить обновления{notice && <span role="status"> — {notice}</span>}</button> : null
  return <section className="update-notice" role="status"><strong>Готова новая версия Academy AI</strong><p>Сохрани текущую работу. Обновление перезагрузит приложение, локальная очередь сохранится.</p>
    {route === 'settings' ? <button className="secondary" disabled={busy} onClick={() => void activate()}>{busy ? 'Обновляем…' : 'Обновить приложение'}</button> : <a href="#settings">Перейти к обновлению</a>}{notice && <p>{notice}</p>}</section>
}
