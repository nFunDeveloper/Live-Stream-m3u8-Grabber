import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 프로덕션 빌드: base '/' (nginx가 루트에서 서빙)
// 개발 서버: base '/develop/' (nginx가 /develop/에서 프록시)
export default defineConfig({
  plugins: [react()],
  base: globalThis.process?.env?.VITE_BASE || '/',
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        // 로컬에서 docker 없이 백엔드를 돌릴 때는 VITE_PROXY_TARGET으로 덮어쓴다
        target: globalThis.process?.env?.VITE_PROXY_TARGET || 'http://backend:10000',
        changeOrigin: true,
      },
      '/detect': {
        target: globalThis.process?.env?.VITE_PROXY_TARGET || 'http://backend:10000',
        changeOrigin: true,
      }
    }
  }
})
