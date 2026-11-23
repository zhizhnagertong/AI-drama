import { Spin } from 'antd'
import { Suspense, lazy, type ReactNode } from 'react'
import { Navigate, createBrowserRouter } from 'react-router'

import { RedirectIfAuthed, RequireAuth } from '@/components/RequireAuth'
import { RootProviders } from '@/components/RootProviders'
import { MainLayout } from '@/layouts/MainLayout'
import { LoginPage } from '@/pages/LoginPage'
import { Workspace } from '@/pages/Workspace'

/**
 * 路由级懒加载：Editor（5 个分区 + 6 个弹窗）与 ProjectDetail 体量大，
 * 单独成 chunk 避免拖累首屏。Workspace 与 LoginPage 保持同步加载。
 */
const Create = lazy(() => import('@/pages/Create').then((m) => ({ default: m.Create })))
const EditorPage = lazy(() => import('@/pages/EditorPage').then((m) => ({ default: m.EditorPage })))
const ProjectDetail = lazy(() =>
  import('@/pages/ProjectDetail').then((m) => ({ default: m.ProjectDetail }))
)
const Mine = lazy(() => import('@/pages/Mine').then((m) => ({ default: m.Mine })))
const Styles = lazy(() => import('@/pages/Styles').then((m) => ({ default: m.Styles })))

function Lazy({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div style={{ minHeight: '60vh', display: 'grid', placeItems: 'center' }}>
          <Spin size="large" />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

/**
 * 路由结构对齐 Vue 版 router/index.js：
 * /login 公开，其余走 RequireAuth；/editor/:id 独立布局（不在 MainLayout 内）。
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootProviders />,
    children: [
      {
        path: 'login',
        element: (
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        )
      },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <MainLayout />,
            children: [
              { index: true, element: <Workspace /> },
              {
                path: 'create',
                element: (
                  <Lazy>
                    <Create />
                  </Lazy>
                )
              },
              {
                path: 'styles',
                element: (
                  <Lazy>
                    <Styles />
                  </Lazy>
                )
              },
              {
                path: 'mine',
                element: (
                  <Lazy>
                    <Mine />
                  </Lazy>
                )
              },
              {
                path: 'project/:id',
                element: (
                  <Lazy>
                    <ProjectDetail />
                  </Lazy>
                )
              }
            ]
          },
          {
            path: 'editor/:id',
            element: (
              <Lazy>
                <EditorPage />
              </Lazy>
            )
          }
        ]
      },
      { path: '*', element: <Navigate to="/" replace /> }
    ]
  }
])