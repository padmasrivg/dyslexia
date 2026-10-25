import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/atkinson-hyperlegible/400.css'
import '@fontsource/atkinson-hyperlegible/700.css'
import '@fontsource/atkinson-hyperlegible-mono/400.css'
import './index.css'
import { PrefsProvider } from './prefs'
import { AgentProvider } from './agent'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PrefsProvider>
      <AgentProvider>
        <App />
      </AgentProvider>
    </PrefsProvider>
  </StrictMode>,
)
