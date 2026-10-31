import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HeroUIProvider } from '@heroui/react'
import './index.css'
import App from './App.jsx'
import PasswordGate from './components/PasswordGate.jsx'

// 라우터 없이 pathname만 본다. 개발 서버는 base가 '/develop/'이라 제거 후 비교.
// /remote 는 별도 페이지가 아니라 '메인 + 원격 제어 드로어가 열린 상태'의 진입점이다.
const basePath = import.meta.env.BASE_URL || '/'
const relativePath = window.location.pathname.startsWith(basePath)
  ? window.location.pathname.slice(basePath.length)
  : window.location.pathname
const isRemoteEntry = relativePath === 'remote' || relativePath.startsWith('remote/')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <HeroUIProvider>
      {/* 비밀번호를 통과하기 전에는 App 이 아예 마운트되지 않는다.
          히스토리를 읽거나 API를 호출하지도 않는다. */}
      <PasswordGate>
        <App initialRemoteOpen={isRemoteEntry} />
      </PasswordGate>
    </HeroUIProvider>
  </StrictMode>,
)