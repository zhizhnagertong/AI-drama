import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { useSessionStore } from '@/store/session'

/** 路由守卫：替代 Vue 版的 router.beforeEach */
export function RequireAuth() {
  const accessToken = useSessionStore((s) => s.accessToken)
  const location = useLocation()

  if (!accessToken) {
    const redirect = location.pathname + location.search
    const target =
      redirect === '/' ? '/login' : `/login?redirect=${encodeURIComponent(redirect)}`
    return <Navigate to={target} replace />
  }

  return <Outlet />
}

/** 已登录用户访问 /login 时回到工作台 */
export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const accessToken = useSessionStore((s) => s.accessToken)
  if (accessToken) return <Navigate to="/" replace />
  return <>{children}</>
}