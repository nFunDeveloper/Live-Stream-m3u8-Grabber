import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HeroUIProvider } from '@heroui/react'
import './index.css'
import App from './App.jsx'
import PasswordGate from './components/PasswordGate.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <HeroUIProvider>
      {/* 비밀번호를 통과하기 전에는 App 이 아예 마운트되지 않는다.
          히스토리를 읽거나 API를 호출하지도 않는다. */}
      <PasswordGate>
        <App />
      </PasswordGate>
    </HeroUIProvider>
  </StrictMode>,
)