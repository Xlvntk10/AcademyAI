import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Download, ShieldCheck, WifiOff } from 'lucide-react'
import { api } from './api'
import { localDay, message, type StudySettings } from './Planner'
import { notifyStudy, getInstallPrompt, clearInstallPrompt, type InstallPrompt } from './pwa'

export function ReminderHost() {
  const [settings, setSettings] = useState<StudySettings | null>(null)
  const [notice, setNotice] = useState('')
  const lastDay = useRef('')
  useEffect(() => {
    const load = () => { void api<StudySettings>('/planner/settings').then(setSettings).catch(() => {}) }
    load(); window.addEventListener('academy-settings-change', load)
    const pwaError = (event: Event) => setNotice((event as CustomEvent<string>).detail)
    window.addEventListener('academy-pwa-error', pwaError)
    return () => { window.removeEventListener('academy-settings-change', load); window.removeEventListener('academy-pwa-error', pwaError) }
  }, [])
  useEffect(() => {
    if (!settings?.reminder_enabled) return
    const check = () => {
      if (document.visibilityState !== 'visible') return
      const now = new Date()
      const time = new Intl.DateTimeFormat('en-GB', { timeZone:'Asia/Almaty', hour:'2-digit', minute:'2-digit', hourCycle:'h23' }).format(now)
      const day = localDay()
      let saved = lastDay.current
      try { saved = localStorage.getItem('academy-reminder-day') || saved } catch { /* Memory fallback. */ }
      if (time !== settings.reminder_time || saved === day) return
      lastDay.current = day
      try { localStorage.setItem('academy-reminder-day',day) } catch { /* In-app reminder still works. */ }
      setNotice('Время для небольшого шага. Твои задания ждут в разделе «План».')
      void notifyStudy().catch(() => {})
    }
    check(); const interval = window.setInterval(check, 30000)
    return () => window.clearInterval(interval)
  }, [settings])
  return notice ? <div className="reminder-toast" role="status"><Bell size={19} /><span>{notice}</span><a href="#plan">К плану</a><button onClick={() => setNotice('')} aria-label="Закрыть напоминание">×</button></div> : null
}

export default function Settings() {
  const [settings, setSettings] = useState<StudySettings | null>(null)
  const [install, setInstall] = useState<InstallPrompt | null>(getInstallPrompt)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const supported = 'Notification' in window && window.isSecureContext
  const [permission, setPermission] = useState(() => 'Notification' in window ? Notification.permission : 'unsupported')
  const load = useCallback(() => api<StudySettings>('/planner/settings').then(setSettings).catch(e => setError(message(e))), [])
  useEffect(() => { void load(); const onPrompt = () => setInstall(getInstallPrompt()); window.addEventListener('academy-install-ready', onPrompt); return () => window.removeEventListener('academy-install-ready', onPrompt) }, [load])
  async function save() {
    if (!settings) return
    setBusy(true); setError(''); setNotice('')
    try {
      setSettings(await api<StudySettings>('/planner/reminder', { reminder_enabled:settings.reminder_enabled, reminder_time:settings.reminder_time }))
      window.dispatchEvent(new Event('academy-settings-change')); setNotice('Время занятий сохранено.')
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  async function askPermission() { try { setPermission(await Notification.requestPermission()) } catch (e) { setError(message(e)) } }
  async function testNotification() { try { await notifyStudy(); setNotice('Запрос на показ уведомления отправлен браузеру.') } catch { setError('Браузер не смог показать уведомление. Напоминание внутри приложения остаётся доступным.') } }
  async function installApp() { if (!install) return; try { await install.prompt(); clearInstallPrompt(); setInstall(null) } catch (e) { setError(message(e)) } }
  return <><div className="page-intro"><p>Настройки пространства</p><h2>Учиться в своём ритме.</h2><span>Напоминания, установка и возможности приложения.</span></div>
    {error && <div className="error-box" role="alert">{error}<button className="text-button" onClick={load}>Повторить</button></div>}{notice && <p className="success-note" role="status">{notice}</p>}
    <div className="settings-grid"><section className="panel settings-panel"><Bell size={24} className="green" /><h3>Время для занятий</h3>{settings ? <form onSubmit={event => { event.preventDefault(); void save() }}><label className="checkbox-label"><input type="checkbox" checked={settings.reminder_enabled} onChange={event => setSettings({...settings,reminder_enabled:event.target.checked})} />Напоминать при открытом приложении</label><label>Время · Asia/Almaty<input type="time" required value={settings.reminder_time} onChange={event => setSettings({...settings,reminder_time:event.target.value})} /></label><p className="small-note">Напоминание появляется в выбранную минуту, когда приложение открыто и видно на экране. Закрытое приложение и сон устройства могут помешать доставке.</p><button className="primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить'}</button></form> : <p className="small-note">Настройки загрузятся после подключения к серверу.</p>}</section>
    <section className="panel settings-panel"><ShieldCheck size={24} className="green" /><h3>Уведомления браузера</h3><p>{!supported ? 'В этом окружении системные уведомления недоступны. Обычно нужны HTTPS или localhost.' : permission === 'granted' ? 'Разрешение получено. Можно проверить уведомление.' : permission === 'denied' ? 'Уведомления запрещены в настройках браузера. Встроенное напоминание продолжит работать.' : 'Браузер спросит разрешение только после нажатия кнопки.'}</p><div className="button-row">{supported && permission === 'default' && <button className="secondary" onClick={askPermission}>Разрешить уведомления</button>}{supported && permission === 'granted' && <button className="secondary" onClick={testNotification}>Проверить уведомление</button>}</div></section>
    <section className="panel settings-panel"><Download size={24} className="green" /><h3>Academy AI как приложение</h3><p>В production-сборке доступен PWA-манифест. Если браузер поддерживает установку, используй кнопку или пункт «Установить приложение» в его меню.</p>{install && <button className="primary" onClick={installApp}>Установить Academy AI</button>}<p className="small-note">На iPhone: Safari → «Поделиться» → «На экран Домой». Для телефона нужен HTTPS. HTTP-адрес компьютера в Wi-Fi подходит для онлайн-интерфейса, но не для полноценной установки PWA.</p></section>
    <section className="panel settings-panel"><WifiOff size={24} className="green" /><h3>Что доступно без сети</h3><p>После первого открытия production-версии кешируется оболочка: страницы, стили и иконки. Загрузка уроков, ответы, план и статистика пока требуют соединения с сервером.</p><p className="small-note">Офлайн-уроки и очередь синхронизации — отдельный следующий этап. Системных виджетов пока нет.</p></section></div>
  </>
}
