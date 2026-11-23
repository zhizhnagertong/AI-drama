/**
 * 会话状态（唯一真源）。
 *
 * 对应 Vue 版 src/api/session.js。原版用模块级 `ref` 规避
 * request → store → request 的循环依赖；React 侧 zustand 的
 * `getState()/setState()` 天生支持组件外读写，所以不再需要两套状态载体，
 * 直接收敛为一个 store，并保留原有的存储键与「记住我」双存储语义。
 */
import { create } from 'zustand'

import type { User } from '@/types'

const ACCESS_KEY = 'auth.access'
const REFRESH_KEY = 'auth.refresh'
const USER_KEY = 'auth.user'
const DEVICE_KEY = 'auth.device'
const REMEMBER_KEY = 'auth.remember'

/* ---------------- 存储容错（隐私模式下 localStorage 可能不可写） ---------------- */

function storages(): Storage[] {
  const list: Storage[] = []
  try {
    list.push(window.localStorage)
  } catch {
    /* ignore */
  }
  try {
    list.push(window.sessionStorage)
  } catch {
    /* ignore */
  }
  return list
}

function safeGet(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(storage: Storage, key: string, value: string): void {
  try {
    storage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

function safeRemove(storage: Storage, key: string): void {
  try {
    storage.removeItem(key)
  } catch {
    /* ignore */
  }
}

/** 跨两种存储读取第一个命中的值（localStorage 优先） */
function readAny(key: string): string {
  for (const s of storages()) {
    const v = safeGet(s, key)
    if (v !== null && v !== '') return v
  }
  return ''
}

function pickStorage(remember: boolean): Storage | null {
  try {
    return remember ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function readRemember(): boolean {
  return storages().some((s) => safeGet(s, REMEMBER_KEY) === '1')
}

/** 设备指纹：首次生成后持久化，用于 refresh_tokens 表标识设备 */
export function deviceId(): string {
  const exist = readAny(DEVICE_KEY)
  if (exist) return exist
  const id = 'dev_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
  for (const s of storages()) safeSet(s, DEVICE_KEY, id)
  return id
}

/* ---------------- Store ---------------- */

export interface SessionPayload {
  access: string
  refresh?: string
  user?: User | null
  expiresIn?: number
  refreshExpiresIn?: number
  remember?: boolean
}

interface SessionState {
  accessToken: string
  refreshToken: string
  user: User | null
  accessExpiresAt: number
  refreshExpiresAt: number
  /** 启动时从存储恢复会话；refresh 已过期则清空并返回 false */
  restore: () => boolean
  /** 登录成功写入（同时落存储） */
  persist: (p: SessionPayload) => void
  /** 无感刷新后仅更新令牌，沿用当前存储策略 */
  updateTokens: (t: { access?: string; refresh?: string; expiresIn?: number }) => void
  setUser: (u: User | null) => void
  clear: () => void
}

export const useSessionStore = create<SessionState>()((set) => ({
  accessToken: '',
  refreshToken: '',
  user: null,
  accessExpiresAt: 0,
  refreshExpiresAt: 0,

  restore() {
    // 旧版单令牌键（token/user）已废弃：静默清除，避免与新会话键混淆
    for (const s of storages()) {
      safeRemove(s, 'token')
      safeRemove(s, 'user')
    }
    const access = readAny(ACCESS_KEY)
    const refresh = readAny(REFRESH_KEY)
    const rawUser = readAny(USER_KEY)
    const accessExp = Number(readAny(`${ACCESS_KEY}.exp`) || 0)
    const refreshExp = Number(readAny(`${REFRESH_KEY}.exp`) || 0)

    let user: User | null = null
    if (rawUser) {
      try {
        user = JSON.parse(rawUser) as User
      } catch {
        user = null
      }
    }

    set({
      accessToken: access,
      refreshToken: refresh,
      user,
      accessExpiresAt: accessExp,
      refreshExpiresAt: refreshExp
    })

    if (refresh && refreshExp && refreshExp <= Date.now()) {
      useSessionStore.getState().clear()
      return false
    }
    return !!refresh
  },

  persist({ access, refresh, user, expiresIn, refreshExpiresIn, remember = false }) {
    const store = pickStorage(remember)
    const other = pickStorage(!remember)
    const now = Date.now()

    if (store) {
      safeSet(store, ACCESS_KEY, access)
      if (refresh) safeSet(store, REFRESH_KEY, refresh)
      safeSet(store, REMEMBER_KEY, remember ? '1' : '0')
      if (user) safeSet(store, USER_KEY, JSON.stringify(user))
      if (expiresIn) safeSet(store, `${ACCESS_KEY}.exp`, String(now + expiresIn * 1000))
      if (refreshExpiresIn) {
        safeSet(store, `${REFRESH_KEY}.exp`, String(now + refreshExpiresIn * 1000))
      }
    }
    // 切换「记住我」策略时清掉另一侧会话，避免双份登录态
    if (other) {
      safeRemove(other, ACCESS_KEY)
      safeRemove(other, REFRESH_KEY)
      safeRemove(other, USER_KEY)
    }

    set({
      accessToken: access,
      refreshToken: refresh || '',
      user: user ?? null,
      accessExpiresAt: expiresIn ? now + expiresIn * 1000 : 0,
      refreshExpiresAt: refreshExpiresIn ? now + refreshExpiresIn * 1000 : 0
    })
  },

  updateTokens({ access, refresh, expiresIn }) {
    const store = pickStorage(readRemember())
    if (store) {
      if (access) safeSet(store, ACCESS_KEY, access)
      if (refresh) safeSet(store, REFRESH_KEY, refresh)
      if (expiresIn) {
        safeSet(store, `${ACCESS_KEY}.exp`, String(Date.now() + expiresIn * 1000))
      }
    }
    set((state) => ({
      accessToken: access ?? state.accessToken,
      refreshToken: refresh ?? state.refreshToken,
      accessExpiresAt: expiresIn ? Date.now() + expiresIn * 1000 : state.accessExpiresAt
    }))
  },

  setUser(user) {
    const store = pickStorage(readRemember())
    if (store && user) safeSet(store, USER_KEY, JSON.stringify(user))
    set({ user })
  },

  clear() {
    for (const s of storages()) {
      safeRemove(s, ACCESS_KEY)
      safeRemove(s, REFRESH_KEY)
      safeRemove(s, USER_KEY)
      safeRemove(s, REMEMBER_KEY)
      safeRemove(s, `${ACCESS_KEY}.exp`)
      safeRemove(s, `${REFRESH_KEY}.exp`)
    }
    set({
      accessToken: '',
      refreshToken: '',
      user: null,
      accessExpiresAt: 0,
      refreshExpiresAt: 0
    })
  }
}))

export function isRefreshExpired(): boolean {
  const { refreshToken, refreshExpiresAt } = useSessionStore.getState()
  return !!refreshToken && !!refreshExpiresAt && refreshExpiresAt <= Date.now()
}

/** 组件外读取当前令牌（axios 拦截器用） */
export function getAccessToken(): string {
  return useSessionStore.getState().accessToken
}