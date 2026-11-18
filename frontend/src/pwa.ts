export interface InstallPrompt extends Event { prompt(): Promise<{outcome: string}> }
let pendingInstall: InstallPrompt | null = null
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault()
  pendingInstall = event as InstallPrompt
  window.dispatchEvent(new Event('academy-install-ready'))
})
export const getInstallPrompt = () => pendingInstall
export const clearInstallPrompt = () => { pendingInstall = null }
window.addEventListener('appinstalled', () => {
  clearInstallPrompt()
  window.dispatchEvent(new Event('academy-install-ready'))
})

let pwaRegistration: ServiceWorkerRegistration | null = null
// A first installation can briefly be waiting, but it is not an update.
export const waitingWorker = () => pwaRegistration?.active ? pwaRegistration.waiting : null
export async function checkPwaUpdate() {
  if (!pwaRegistration) throw new Error('Проверка обновлений доступна после регистрации PWA в production-версии по HTTPS или localhost.')
  await pwaRegistration.update()
}
let shellReady = false
export const offlineShellReady = () => shellReady

async function inspectShell(registration: ServiceWorkerRegistration) {
  // Check the worker controlling this document, including during an update.
  const worker = navigator.serviceWorker.controller
  if (!worker || !registration.active) return
  const channel = new MessageChannel()
  const timeout = window.setTimeout(() => channel.port1.close(), 5000)
  channel.port1.onmessage = event => {
    clearTimeout(timeout); channel.port1.close()
    shellReady = event.data?.ready === true
    window.dispatchEvent(new Event('academy-shell-status'))
  }
  worker.postMessage({ type: 'CHECK_OFFLINE_SHELL' }, [channel.port2])
}

export async function registerPwa(): Promise<void> {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator) || !window.isSecureContext) return
  // An installed worker can boot offline even if fetching /sw.js fails.
  // Bind it before attempting the network-dependent registration/update.
  const bind = (registration: ServiceWorkerRegistration) => {
    pwaRegistration = registration
    void inspectShell(registration)
    // Notify on activation too, so the UI clears an already displayed notice.
    const announce = () => window.dispatchEvent(new Event('academy-update-ready'))
    announce()
    registration.addEventListener('updatefound', () => {
      registration.installing?.addEventListener('statechange', announce)
    })
  }
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (pwaRegistration) void inspectShell(pwaRegistration) })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void checkPwaUpdate().catch(() => {})
  })
  try {
    const existing = await navigator.serviceWorker.getRegistration('/')
    if (existing) bind(existing)
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' })
    if (registration !== existing) bind(registration)
    void navigator.serviceWorker.ready.then(() => inspectShell(registration))
  }
  catch {
    if (!pwaRegistration?.active) window.dispatchEvent(new CustomEvent('academy-pwa-error', { detail: 'Кеш приложения пока не подготовлен. Подключись к серверу для первого автономного запуска.' }))
  }
}

export async function notifyStudy(): Promise<void> {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const registration = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : undefined
  const options = { body: 'Небольшой шаг сегодня — больше знаний завтра. Открой свой учебный план.', icon: '/icons/icon-192.png', tag: 'academy-study-reminder' }
  if (registration) await registration.showNotification('Время для Academy AI', options)
  else new Notification('Время для Academy AI', options)
}
