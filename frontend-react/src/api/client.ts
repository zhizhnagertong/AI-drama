/**
 * axios 实例 + 无感刷新（全局单飞）+ 统一错误处理。
 *
 * 移植自 Vue 版 src/api/index.js，逻辑完全等价，差异只有：
 * - 令牌来源从模块级 ref 改为 zustand `getState()`；
 * - 会话失效不再直接 import router（避免与路由守卫循环依赖），
 *   改为广播事件，由 RootProviders 订阅后跳转。
 */
import axios from 'axios'
import type { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

import { toast } from '@/lib/feedback'
import { emitSessionExpired } from '@/lib/sessionEvents'
import { deviceId, isRefreshExpired, useSessionStore } from '@/store/session'
import type { ApiErrorBody } from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

/** 登录/注册/找回密码类接口的错误交给表单回显，不弹全局 toast、不触发刷新 */
const AUTH_ENDPOINT = /\/auth\/(login|register|verify-user|password|refresh)/

export interface ApiError extends Error {
  status?: number
  bizCode?: string
  fieldErrors?: Record<string, string>
  friendlyMessage?: string
}

type RetryableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

/* ---------------- 请求拦截：注入 Bearer + 设备指纹 ---------------- */
api.interceptors.request.use((config) => {
  const { accessToken } = useSessionStore.getState()
  if (accessToken) config.headers.set('Authorization', `Bearer ${accessToken}`)
  config.headers.set('X-Device-Id', deviceId())
  return config
})

/* ---------------- 无感刷新（全局单飞） ---------------- */
let refreshing: Promise<string> | null = null

/**
 * 刷新 access 令牌。全局共享同一个 in-flight Promise：
 * 后端每次刷新都会轮换并作废旧 refresh，若两条路径并发用同一个旧 refresh，
 * 后一个会被判 REFRESH_REVOKED 而误清会话。所有调用方必须走这里。
 */
export function refreshOnce(): Promise<string> {
  if (refreshing) return refreshing

  const { refreshToken } = useSessionStore.getState()
  if (!refreshToken || isRefreshExpired()) {
    return Promise.reject(new Error('NO_REFRESH'))
  }

  refreshing = axios
    .post(
      '/api/v1/auth/refresh',
      { refresh_token: refreshToken },
      { headers: { 'X-Device-Id': deviceId() } }
    )
    .then((res) => {
      const data = (res.data || {}) as { access_token?: string; refresh_token?: string; expires_in?: number }
      if (!data.access_token) throw new Error('NO_REFRESH')
      useSessionStore.getState().updateTokens({
        access: data.access_token,
        refresh: data.refresh_token,
        expiresIn: data.expires_in
      })
      return data.access_token
    })
    .finally(() => {
      refreshing = null
    })

  return refreshing
}

function handleSessionExpired(): void {
  useSessionStore.getState().clear()
  emitSessionExpired('会话已失效，请重新登录')
}

/* ---------------- 响应拦截：401 重放 + 统一错误归一 ---------------- */
api.interceptors.response.use(
  (res: AxiosResponse) => res,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as RetryableConfig | undefined
    const status = error.response?.status
    const body = error.response?.data ?? {}
    const detail = body.message ?? body.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : error.message || '请求失败'

    const isAuthEndpoint = AUTH_ENDPOINT.test(config?.url || '')
    const { refreshToken } = useSessionStore.getState()

    // 401：尝试无感刷新后重放原请求（仅一次）
    if (status === 401 && config && !config._retried && !isAuthEndpoint && refreshToken) {
      try {
        const newToken = await refreshOnce()
        config._retried = true
        config.headers.set('Authorization', `Bearer ${newToken}`)
        return api(config)
      } catch (refreshErr) {
        // 服务端明确拒绝刷新（有 response）→ 会话失效；网络原因 → 保留会话。
        // refreshOnce 在「无 refresh / refresh 已过期」时抛本地 Error（无 response），
        // 此时刷新已无可能，必须同样按会话失效处理，否则用户会卡在 401 且不会跳登录页。
        const definitive = !!(refreshErr as { response?: unknown })?.response
        if (definitive || (refreshErr as Error)?.message === 'NO_REFRESH') {
          handleSessionExpired()
        }
        throw error
      }
    }

    if (status === 401 && !isAuthEndpoint) {
      handleSessionExpired()
      throw error
    }

    if (!isAuthEndpoint) toast.error(msg)

    const apiError = error as ApiError
    apiError.status = status
    apiError.bizCode = body.biz_code
    apiError.fieldErrors = body.field_errors
    apiError.friendlyMessage = msg
    throw apiError
  }
)

/** 兼容两种返回结构：裸 payload 或 {code, message, data: payload} */
export function unwrap<T>(res: AxiosResponse): T {
  const body = (res?.data !== undefined ? res.data : res) as unknown
  if (
    body &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    'data' in (body as Record<string, unknown>) &&
    ('code' in (body as Record<string, unknown>) || 'message' in (body as Record<string, unknown>)) &&
    !('id' in (body as Record<string, unknown>))
  ) {
    return (body as Record<string, unknown>).data as T
  }
  return body as T
}

export default api