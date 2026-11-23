import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'

// 顺序与 Vue 版一致：tokens → 全局 → 页面/布局
import '@/styles/tokens.css'
import '@/styles/main.css'
import '@/styles/auth.css'
import '@/styles/layout.css'
import '@/styles/workspace.css'
import '@/styles/editor.css'
import '@/styles/create.css'
import '@/styles/mine.css'
import '@/styles/styles-page.css'
import '@/styles/taskprogress.css'
import '@/styles/project-detail.css'

import { router } from '@/router'
import { useThemeStore } from '@/store/theme'

// 渲染前先落主题，避免深色用户看到一帧白屏
useThemeStore.getState().apply()

const container = document.getElementById('root')
if (!container) throw new Error('#root not found')

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>
)