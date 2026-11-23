/**
 * 认证动作（对应 Vue 版 stores/auth.js）。
 *
 * 与 Pinia 版的差异：这里不再 import router。登出后的跳转交给调用方，
 * 避免 store → router → 守卫 → store 的循环依赖。
 */
import { create } from 'zustand'

import { authApi, type RegisterPayload } from '@/api/auth'
import { refreshOnce } from '@/api/client'
import { isRefreshExpired, useSessionStore } from '@/store/session'
import type { LoginResult } from '@/types'

interface AuthState {
  initialized: boolean
  /** 启动时恢复会话：仅当 access 已过期/缺失时才续期，避免无谓换票 */
  init: () => Promise<void>
  login: (username: string, password: string, remember?: boolean) => Promise<LoginResult>
  register: (payload: RegisterPayload) => Promise<unknown>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>()((set) => ({
  initialized: false,

  async init() {
    const restored = useSessionStore.getState().restore()
    if (!restored) {
      set({ initialized: true })
      return
    }
    if (isRefreshExpired()) {
      useSessionStore.getState().clear()
      set({ initialized: true })
      return
    }
    const { accessToken, accessExpiresAt } = useSessionStore.getState()
    const stillValid = accessToken && accessExpiresAt > Date.now() + 30_000
    if (stillValid) {
      set({ initialized: true })
      return
    }
    try {
      // 统一走 refreshOnce：与请求拦截器共享同一 in-flight，避免轮换竞争
      await refreshOnce()
    } catch {
      /* 刷新失败已由拦截器广播处理 */
    }
    set({ initialized: true })
  },

  async login(username, password, remember = false) {
    const data = await authApi.login(username, password, remember)
    const access = data?.access_token || ''
    if (!access) throw new Error('登录返回缺少 token')
    useSessionStore.getState().persist({
      access,
      refresh: data.refresh_token,
      user: data.user || { username, nickname: username },
      expiresIn: data.expires_in,
      refreshExpiresIn: data.refresh_expires_in,
      remember
    })
    return data
  },

  /** 注册成功后不自动登录（对齐规范：由用户自行登录） */
  register(payload) {
    return authApi.register(payload)
  },

  async logout() {
    const { refreshToken } = useSessionStore.getState()
    try {
      if (refreshToken) await authApi.logout(refreshToken)
    } catch {
      /* 网络失败不阻塞本地登出 */
    }
    useSessionStore.getState().clear()
  }
}))