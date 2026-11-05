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
export const waitingWorker = () => pwaRegistration?.waiting ?? null
export async function checkPwaUpdate() { await pwaRegistration?.update() }
let shellReady = false
export const offlineShellReady = () => shellReady

async function inspectShell(registration: ServiceWorkerRegistration) {
  if (!registration.active) return
  const channel = new MessageChannel()
  const timeout = window.setTimeout(() => channel.port1.close(), 5000)
  channel.port1.onmessage = event => {
    clearTimeout(timeout); channel.port1.close()
    shellReady = event.data?.ready === true
    window.dispatchEvent(new Event('academy-shell-status'))
  }
  registration.active.postMessage({ type: 'CHECK_OFFLINE_SHELL' }, [channel.port2])
}

export async function registerPwa(): Promise<void> {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator) || !window.isSecureContext) return
  try {
    pwaRegistration = await navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
    void navigator.serviceWorker.ready.then(inspectShell)
    navigator.serviceWorker.addEventListener('controllerchange', () => { if (pwaRegistration) void inspectShell(pwaRegistration) })
    const announce = () => { if (pwaRegistration?.waiting) window.dispatchEvent(new Event('academy-update-ready')) }
    announce()
    pwaRegistration.addEventListener('updatefound', () => {
      pwaRegistration?.installing?.addEventListener('statechange', announce)
    })
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void checkPwaUpdate().catch(() => {})
    })
  }
  catch { window.dispatchEvent(new CustomEvent('academy-pwa-error', { detail: 'Не удалось подготовить кеш приложения. Основные функции доступны онлайн.' })) }
}

export async function notifyStudy(): Promise<void> {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  const registration = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : undefined
  const options = { body: 'Небольшой шаг сегодня — больше знаний завтра. Открой свой учебный план.', icon: '/icons/icon-192.png', tag: 'academy-study-reminder' }
  if (registration) await registration.showNotification('Время для Academy AI', options)
  else new Notification('Время для Academy AI', options)
}
