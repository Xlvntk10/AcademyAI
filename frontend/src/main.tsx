import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'
import './platform.css'
import { registerPwa } from './pwa'
import { AccountGate } from './Account'
import { MagicLinkCallback, readLinkCallback } from './MagicLink'

const callback = readLinkCallback()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{callback ? <MagicLinkCallback callback={callback}/> : <AccountGate><App /></AccountGate>}</React.StrictMode>,
)
void registerPwa()
