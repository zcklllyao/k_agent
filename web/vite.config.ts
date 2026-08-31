import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// 前端开发服务器：/api 默认代理到本地开发 API 8001；可用 VITE_API_PROXY_TARGET 覆盖
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // 本机 8000 端口有遗留旧进程；当前 API 统一运行在 8001，避免网页请求落到旧实例。
        target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
