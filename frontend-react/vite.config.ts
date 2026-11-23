import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5174,
    watch: {
      // 编辑器/工具写入文件时会生成原子临时目录，被 dev server 监听到会抛 EBUSY 直接崩掉
      ignored: ['**/.*.tmpdir/**', '**/*.tmp', '**/dist/**']
    },
    proxy: {
      // 与 Vue 版保持一致的后端代理（backend 默认 8010）
      '/api': { target: 'http://localhost:8010', changeOrigin: true },
      '/static': { target: 'http://localhost:8010', changeOrigin: true }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false
  }
})