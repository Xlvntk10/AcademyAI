import { useEffect, useRef, useState } from 'react'
import { Mic, Play, Square, Volume2 } from 'lucide-react'

export function ListeningAudio({ transcript, onMode }: { transcript: string; onMode: (mode: 'text' | 'audio') => void }) {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [shown, setShown] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!('speechSynthesis' in window)) return
    const load = () => setVoices(speechSynthesis.getVoices().filter(v => v.localService && /^en(?:[-_]|$)/i.test(v.lang)))
    load(); speechSynthesis.addEventListener('voiceschanged', load)
    return () => { speechSynthesis.cancel(); speechSynthesis.removeEventListener('voiceschanged', load) }
  }, [])
  function play() {
    try {
      speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(transcript)
      utterance.voice = voices[0]; utterance.lang = voices[0].lang; utterance.rate = .92
      utterance.onerror = () => setError('Синтез речи недоступен. Можно перейти в текстовый режим.')
      speechSynthesis.speak(utterance); onMode(shown ? 'text' : 'audio'); setError('')
    } catch { setError('Не удалось запустить голос. Используй текстовый режим.') }
  }
  return <section className="panel media-panel"><Volume2 className="green" /><h3>Учебное аудио</h3><p className="small-note">Используется только локальный английский голос браузера. Это синтез речи, без естественной беседы и разнообразия акцентов настоящего экзамена.</p><div className="button-row"><button className="primary compact" disabled={!voices.length} onClick={play}><Play size={15} />Слушать</button><button className="secondary compact" onClick={() => { if ('speechSynthesis' in window) speechSynthesis.cancel() }}><Square size={14} />Стоп</button><button className="text-button" onClick={() => { setShown(true); onMode('text') }}>Открыть текст</button></div>{!voices.length && <p className="small-note">Локальный английский голос не найден. Доступна практика по тексту; результат будет помечен как текстовый.</p>}{error && <p role="alert">{error}</p>}{shown && <p className="practice-passage" lang="en">{transcript}</p>}</section>
}

function audioDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('academy-local-recordings', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('clips')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}
export async function localClip(id: string, blob?: Blob): Promise<Blob | undefined> {
  const db = await audioDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction('clips', blob ? 'readwrite' : 'readonly')
      const request = blob ? transaction.objectStore('clips').put(blob, id) : transaction.objectStore('clips').get(id)
      transaction.oncomplete = () => resolve(blob ?? request.result)
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error)
    })
  } finally { db.close() }
}

export function SpeakingRecorder({ id, disabled, onMode, onRecording, expectedAudio = false }: { id: string; disabled: boolean; onMode: (mode: 'audio') => void; onRecording: (value: boolean) => void; expectedAudio?: boolean }) {
  const [recording, setRecording] = useState(false)
  const [pending, setPending] = useState(false)
  const [clip, setClip] = useState<Blob | null>(null)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const live = useRef(true)
  const supported = window.isSecureContext && !!navigator.mediaDevices?.getUserMedia && 'MediaRecorder' in window
  useEffect(() => {
    live.current = true
    if ('indexedDB' in window) void localClip(id).then(blob => {
      if (!live.current) return
      if (blob) { setClip(blob); if (!disabled) onMode('audio') }
      else if (expectedAudio) setError('Локальная запись на этом устройстве не найдена. Она могла остаться в другом браузере или быть удалена при очистке данных.')
    }).catch(() => { if (live.current && expectedAudio) setError('Не удалось открыть локальную запись. Сохранённый текст остаётся доступным.') })
    return () => { live.current = false; window.clearTimeout(timer.current); if (recorder.current?.state === 'recording') recorder.current.stop(); stream.current?.getTracks().forEach(t => t.stop()) }
  }, [id])
  useEffect(() => { if (!clip) return; const address = URL.createObjectURL(clip); setUrl(address); return () => URL.revokeObjectURL(address) }, [clip])
  async function start() {
    setError(''); setPending(true); onRecording(true)
    try {
      const input = await navigator.mediaDevices.getUserMedia({audio:true})
      if (!live.current) { input.getTracks().forEach(t => t.stop()); return }
      setPending(false)
      stream.current = input
      const capture = new MediaRecorder(input); recorder.current = capture
      const chunks: BlobPart[] = []
      capture.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      capture.onstop = () => {
        window.clearTimeout(timer.current); input.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunks, {type:capture.mimeType || 'audio/webm'})
        if (!blob.size) { if (live.current) { setRecording(false); onRecording(false); setError('Запись пуста. Попробуй снова или используй текст.') }; return }
        if (live.current) { setClip(blob); setRecording(false); onRecording(false); onMode('audio') }
        void localClip(id,blob).catch(() => { if (live.current) setError('Не удалось сохранить аудио в браузере. Скачай запись, пока страница открыта.') })
      }
      capture.onerror = () => { input.getTracks().forEach(t => t.stop()); if (live.current) { setRecording(false); onRecording(false); setError('Ошибка записи. Текстовый режим доступен.') } }
      capture.start(); setRecording(true)
      timer.current = window.setTimeout(() => { if (capture.state === 'recording') capture.stop() }, 300000)
    } catch { stream.current?.getTracks().forEach(t => t.stop()); if (live.current) { setPending(false); setRecording(false); onRecording(false); setError('Микрофон недоступен или разрешение не выдано. Напиши ответ в текстовом поле.') } }
  }
  return <section className="panel media-panel"><Mic className="green" /><h3>Твоя речь</h3><p className="small-note">Аудио остаётся в этом браузере (IndexedDB), на сервер не отправляется и между устройствами не переносится. Скачай важную запись. Очистка данных браузера удалит локальную копию. Максимум 5 минут.</p>{supported ? <div className="button-row"><button className="secondary compact" disabled={disabled || recording || pending} onClick={start}>{clip ? 'Записать заново' : 'Записать голос'}</button>{recording && <button className="primary compact" onClick={() => recorder.current?.stop()}><Square size={14} />Остановить запись</button>}</div> : <p>Запись недоступна: нужен поддерживаемый браузер и HTTPS или localhost. Используй текстовый ответ ниже.</p>}{pending && <p role="status">Ожидаем разрешение микрофона…</p>}{recording && <p role="status">Идёт запись. Останови её перед завершением работы.</p>}{url && <><audio controls src={url} /><a className="text-button" href={url} download={`academy-${id}.${clip?.type.includes('mp4') ? 'm4a' : 'webm'}`}>Скачать аудио</a></>}{error && <p role="alert">{error}</p>}</section>
}
