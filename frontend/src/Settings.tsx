import { privateKey } from './account-context'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Download, ShieldCheck, WifiOff } from 'lucide-react'
import { api } from './api'
import { localDay, message, type StudySettings } from './Planner'
import { notifyStudy, getInstallPrompt, clearInstallPrompt, type InstallPrompt } from './pwa'

const reminderKey = 'academy-reminder-preferences-v1'
const reminderDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
function cacheReminder(settings: StudySettings) {
  try { localStorage.setItem(privateKey(reminderKey), JSON.stringify({ reminder_enabled: settings.reminder_enabled,
    reminder_time: settings.reminder_time, reminder_days: settings.reminder_days ?? [0,1,2,3,4,5,6], timezone: settings.timezone })) } catch { /* Online settings remain available. */ }
}

export function reminderDue(settings: Pick<StudySettings, 'reminder_time' | 'reminder_days' | 'timezone'>, now: Date) {
  const timezone = settings.timezone || 'Asia/Almaty'
  const time = new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now)
  const weekday = new Intl.DateTimeFormat('en-US', { timeZone: timezone, weekday: 'short' }).format(now)
  return time === settings.reminder_time && (settings.reminder_days ?? [0,1,2,3,4,5,6]).includes(['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(weekday))
}

export function ReminderHost() {
  const [settings, setSettings] = useState<StudySettings | null>(null)
  const [notice, setNotice] = useState('')
  const lastDay = useRef('')
  useEffect(() => {
    try { const cached = localStorage.getItem(privateKey(reminderKey)); if (cached) setSettings(JSON.parse(cached)) } catch { /* Invalid preferences are replaced on connection. */ }
    const load = () => { void api<StudySettings>('/planner/settings').then(value => { cacheReminder(value); setSettings(value) }).catch(() => {}) }
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
      const day = localDay()
      let saved = lastDay.current
      try { saved = localStorage.getItem(privateKey('academy-reminder-day')) || saved } catch { /* Memory fallback. */ }
      if (!reminderDue(settings, now) || saved === day) return
      lastDay.current = day
      try { localStorage.setItem(privateKey('academy-reminder-day'),day) } catch { /* In-app reminder still works. */ }
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
  const [targetDate, setTargetDate] = useState('')
  const supported = 'Notification' in window && window.isSecureContext
  const [permission, setPermission] = useState(() => 'Notification' in window ? Notification.permission : 'unsupported')
  const load = useCallback(() => api<StudySettings>('/planner/settings').then(value => { setSettings(value); cacheReminder(value); setTargetDate(value.masters_target_date ?? '') }).catch(e => setError(message(e))), [])
  useEffect(() => { void load(); const onPrompt = () => setInstall(getInstallPrompt()); window.addEventListener('academy-install-ready', onPrompt); return () => window.removeEventListener('academy-install-ready', onPrompt) }, [load])
  async function save() {
    if (!settings) return
    setBusy(true); setError(''); setNotice('')
    try {
      const saved = await api<StudySettings>('/planner/reminder', { sync_revision:settings.sync_revision, reminder_enabled:settings.reminder_enabled, reminder_time:settings.reminder_time, reminder_days: settings.reminder_days ?? [0,1,2,3,4,5,6] })
      setSettings(saved); cacheReminder(saved)
      window.dispatchEvent(new Event('academy-settings-change')); setNotice('Время занятий сохранено.')
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  async function askPermission() { try { setPermission(await Notification.requestPermission()) } catch (e) { setError(message(e)) } }
  async function testNotification() { try { await notifyStudy(); setNotice('Запрос на показ уведомления отправлен браузеру.') } catch { setError('Браузер не смог показать уведомление. Напоминание внутри приложения остаётся доступным.') } }
  async function installApp() { if (!install) return; try { await install.prompt(); clearInstallPrompt(); setInstall(null) } catch (e) { setError(message(e)) } }
  async function saveTarget() {
    if (!settings) return
    setBusy(true); setError('')
    try {
      const { timezone: _timezone, ...payload } = settings
      const saved = await api<StudySettings>('/planner/settings', { ...payload, masters_target_date: targetDate || null })
      setSettings(saved); setNotice('Дата для обратного отсчёта сохранена.')
    } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <><div className="page-intro"><p>Настройки пространства</p><h2>Учиться в своём ритме.</h2><span>Напоминания, установка и возможности приложения.</span></div>
    {error && <div className="error-box" role="alert">{error}<button className="text-button" onClick={load}>Повторить</button></div>}{notice && <p className="success-note" role="status">{notice}</p>}
    <div className="settings-grid"><section className="panel settings-panel"><Bell size={24} className="green" /><h3>Время для занятий</h3>{settings ? <form onSubmit={event => { event.preventDefault(); void save() }}><label className="checkbox-label"><input type="checkbox" checked={settings.reminder_enabled} onChange={event => setSettings({...settings,reminder_enabled:event.target.checked})} />Напоминать при открытом приложении</label><label>Время · Asia/Almaty<input type="time" required value={settings.reminder_time} onChange={event => setSettings({...settings,reminder_time:event.target.value})} /></label><fieldset className="reminder-days"><legend>Дни занятий</legend>{reminderDays.map((day, index) => <label key={day}><input type="checkbox" checked={(settings.reminder_days ?? [0,1,2,3,4,5,6]).includes(index)} onChange={event => { const selected = settings.reminder_days ?? [0,1,2,3,4,5,6]; setSettings({ ...settings, reminder_days: event.target.checked ? [...selected, index].sort() : selected.filter(value => value !== index) }) }}/>{day}</label>)}</fieldset><p className="small-note">Напоминание появляется в выбранную минуту, когда приложение открыто и видно на экране. Закрытое приложение и сон устройства могут помешать доставке.</p><button className="primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить'}</button></form> : <p className="small-note">Настройки загрузятся после подключения к серверу.</p>}</section>
    <section className="panel settings-panel"><ShieldCheck size={24} className="green" /><h3>Уведомления браузера</h3><p>{!supported ? 'В этом окружении системные уведомления недоступны. Обычно нужны HTTPS или localhost.' : permission === 'granted' ? 'Разрешение получено. Можно проверить уведомление.' : permission === 'denied' ? 'Уведомления запрещены в настройках браузера. Встроенное напоминание продолжит работать.' : 'Браузер спросит разрешение только после нажатия кнопки.'}</p><div className="button-row">{supported && permission === 'default' && <button className="secondary" onClick={askPermission}>Разрешить уведомления</button>}{supported && permission === 'granted' && <button className="secondary" onClick={testNotification}>Проверить уведомление</button>}</div></section>
    <section className="panel settings-panel"><Download size={24} className="green" /><h3>Academy AI как приложение</h3><p>В production-сборке доступен PWA-манифест. Если браузер поддерживает установку, используй кнопку или пункт «Установить приложение» в его меню.</p>{install && <button className="primary" onClick={installApp}>Установить Academy AI</button>}<p className="small-note">На iPhone: Safari → «Поделиться» → «На экран Домой». Для телефона нужен HTTPS. HTTP-адрес компьютера в Wi-Fi подходит для онлайн-интерфейса, но не для полноценной установки PWA.</p></section>
    <section className="panel settings-panel"><WifiOff size={24} className="green" /><h3>Учебная библиотека на устройстве</h3><p>Заранее скачанные уроки доступны без сети. Ответы и черновики сохраняются в браузере. При открытом приложении очередь отправляется на доступный домашний сервер.</p><a className="secondary" href="#offline">Открыть локальную библиотеку</a><p className="small-note">Проверка ответов и начисление XP выполняются сервером. Для нового IELTS-теста, плана и общей статистики требуется соединение.</p></section>
    <section className="panel settings-panel"><h3>Магистратура — обратный отсчёт</h3><p>Выбери личную целевую дату. Она будет доступна общему API будущих виджетов.</p><form onSubmit={event => { event.preventDefault(); void saveTarget() }}><label>Целевая дата<input type="date" value={targetDate} onChange={event => setTargetDate(event.target.value)}/></label><button className="secondary" disabled={!settings || busy}>Сохранить дату</button></form></section></div>
  </>
}
