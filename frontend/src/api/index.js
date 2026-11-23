import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import {
  accessToken,
  refreshToken,
  clearSession,
  emitSessionExpired,
  updateTokens,
  isRefreshExpired,
  deviceId,
  sessionEpoch
} from './session'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

// ---------------- 请求拦截：注入 Bearer + 设备指纹 ----------------
api.interceptors.request.use((config) => {
  if (accessToken.value) {
    config.headers.Authorization = `Bearer ${accessToken.value}`
  }
  config.headers['X-Device-Id'] = deviceId()
  return config
})

// ---------------- 无感刷新（全局单飞：并发只刷一次） ----------------
let refreshing = null

/**
 * 刷新 access 令牌。全局共享同一个 in-flight Promise：
 * 后端每次刷新都会轮换并作废旧 refresh，若两条路径并发用同一个旧 refresh，
 * 后一个会被判 REFRESH_REVOKED 而误清会话。所有调用方必须走这里。
 *
 * 失败时**不**清空会话（由调用方按自身语境决定），仅当 refresh 明确失效才抛错。
 */
export function refreshOnce() {
  if (refreshing) return refreshing
  if (!refreshToken.value || isRefreshExpired()) {
    return Promise.reject(new Error('NO_REFRESH'))
  }
  const epochAtStart = sessionEpoch.value
  // 用裸 axios 绕过本拦截器，避免递归与误触发全局登出
  refreshing = axios
    .post('/api/v1/auth/refresh', { refresh_token: refreshToken.value }, {
      headers: { 'X-Device-Id': deviceId() }
    })
    .then((res) => {
      const data = res.data || {}
      if (!data.access_token) throw new Error('NO_REFRESH')
      // 请求期间用户已登出/会话已失效：丢弃这批令牌，不能写回存储
      if (epochAtStart !== sessionEpoch.value) {
        const err = new Error('LOGGED_OUT')
        err.refreshDefinitive = false
        throw err
      }
      updateTokens({
        access: data.access_token,
        refresh: data.refresh_token,
        expiresIn: data.expires_in,
        refreshExpiresIn: data.refresh_expires_in
      })
      return data.access_token
    })
    .catch((err) => {
      // 仅服务端明确拒绝（有响应）才算令牌失效；网络抖动/超时保留会话，下次再试
      err.refreshDefinitive = !!err.response
      throw err
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

// 登录/注册/找回密码等“免登”接口：错误交给表单自行回显，不弹全局 toast、不触发刷新。
// 用精确白名单而非正则：正则 /auth/(...|password|...)/ 会把 /auth/me/password 也误命中，
// 导致改密失败完全静默（既无 toast 也不走 401 分支）。
const AUTH_FREE_PATHS = [
  '/auth/login',
  '/auth/register',
  '/auth/verify-user',
  '/auth/password/send-code',
  '/auth/password/verify-code',
  '/auth/password/reset',
  '/auth/refresh'
]

function isAuthFree(config) {
  const url = config.url || ''
  return AUTH_FREE_PATHS.some((p) => url.includes(p))
}

// 会话失效只提示一次：并发多个 401 时避免重复弹窗与多次 router.push
let sessionExpiredNotified = false

function handleSessionExpired() {
  clearSession()
  if (!sessionExpiredNotified) {
    sessionExpiredNotified = true
    emitSessionExpired('会话已失效，请重新登录')
    setTimeout(() => { sessionExpiredNotified = false }, 3000)
  }
  if (router.currentRoute.value.path !== '/login') {
    router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
  }
}

api.interceptors.response.use(
  (res) => {
    // 后端业务错误带 biz_code 时 HTTP 状态码已非 2xx，不会走到这里
    return res
  },
  async (err) => {
    const status = err.response?.status
    const config = err.config || {}
    const body = err.response?.data || {}
    const detail = body.message || body.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : detail?.msg || err.message || '请求失败'

    // 登录/注册/找回密码接口的错误交给表单自行回显，不弹全局 toast、不触发刷新
    const isAuthEndpoint = isAuthFree(config)

    // 401：尝试无感刷新后重放原请求（仅一次）。刷新统一走 refreshOnce（裸 axios），
    // 失败只抛错不清会话，是否登出由本拦截器下方的明确失效分支决定。
    if (status === 401 && !config._retried && !isAuthEndpoint && refreshToken.value) {
      try {
        const newToken = await refreshOnce()
        config._retried = true
        config.headers = config.headers || {}
        config.headers.Authorization = `Bearer ${newToken}`
        return api(config)
      } catch (refreshErr) {
        // 服务端明确拒绝刷新 → 会话失效；网络原因 → 保留会话，按原 401 提示
        if (refreshErr?.refreshDefinitive !== false) {
          handleSessionExpired()
        }
        return Promise.reject(err)
      }
    }

    if (status === 401 && !isAuthEndpoint) {
      handleSessionExpired()
      return Promise.reject(err)
    }

    if (!isAuthEndpoint) {
      ElMessage.error(msg)
    }
    err.bizCode = body.biz_code
    err.fieldErrors = body.field_errors
    err.friendlyMessage = msg
    return Promise.reject(err)
  }
)

/**
 * 兼容两种返回结构：裸 payload 或 {code, message, data: payload}
 */
export function unwrap(res) {
  const body = res && res.data !== undefined ? res.data : res
  if (
    body &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    'data' in body &&
    ('code' in body || 'message' in body) &&
    !('id' in body)
  ) {
    return body.data
  }
  return body
}

export default api
