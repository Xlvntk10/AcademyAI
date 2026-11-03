export interface InstallPrompt extends Event { prompt(): Promise<{outcome: string}> }
let pendingInstall: InstallPrompt | null = null
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault()
  pendingInstall = event as InstallPrompt
  window.dispatchEvent(new Event('academy-install-ready'))
})
export const getInstallPrompt = () => pendingInstall
export const clearInstallPrompt = () => { pendingInstall = null }

export async function registerPwa(): Promise<void> {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator) || !window.isSecureContext) return
  try { await navigator.serviceWorker.register('/sw.js') }
  catch { window.dispatchEvent(new CustomEvent('academy-pwa-error', { detail: 'Не удалось подготовить кеш приложения. Основные функции доступны онлайн.' })) }
}

export async function notifyStudy(): Promise<void> {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const registration = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : undefined
  const options = { body: 'Небольшой шаг сегодня — больше знаний завтра. Открой свой учебный план.', icon: '/icons/icon-192.png', tag: 'academy-study-reminder' }
  if (registration) await registration.showNotification('Время для Academy AI', options)
  else new Notification('Время для Academy AI', options)
}
