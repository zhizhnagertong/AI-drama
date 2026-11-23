import { defineStore } from 'pinia'
import api, { unwrap, refreshOnce } from '../api'
import {
  accessToken,
  refreshToken,
  currentUser,
  accessExpiresAt,
  restoreSession,
  persistSession,
  clearSession,
  setUser as persistUser,
  isRefreshExpired
} from '../api/session'
import router from '../router'

export const useAuthStore = defineStore('auth', {
  state: () => ({}),
  getters: {
    token: () => accessToken.value,
    user: () => currentUser.value,
    isLoggedIn: () => !!accessToken.value,
    displayName: () =>
      currentUser.value?.nickname || currentUser.value?.username || currentUser.value?.name || '创作者'
  },
  actions: {
    /** 启动时恢复会话；仅当 access 已过期/缺失时才续期，避免无谓换票 */
    async init() {
      if (!restoreSession()) return
      if (isRefreshExpired()) {
        clearSession()
        return
      }
      const stillValid = accessToken.value && accessExpiresAt.value > Date.now() + 30_000
      if (stillValid) return
      try {
        // 统一走 refreshOnce：与请求拦截器共享同一 in-flight，避免轮换竞争
        await refreshOnce()
      } catch {
        /* 刷新失败已由拦截器广播处理 */
      }
    },
    async login(username, password, remember = false) {
      const data = unwrap(
        await api.post('/auth/login', { username, password, remember })
      )
      const access = data?.access_token || ''
      if (!access) throw new Error('登录返回缺少 token')
      persistSession({
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
    async register(payload) {
      const data = unwrap(await api.post('/auth/register', payload))
      return data
    },
    setUser(user) {
      persistUser(user)
    },
    async logout() {
      const rt = refreshToken.value
      // 先本地登出：clearSession 会自增 sessionEpoch，作废所有在途刷新结果，
      // 避免"后台刷新在登出后返回、把新令牌写回存储"导致退不出去。
      clearSession()
      router.push('/login')
      // 再异步通知服务端撤销 refresh 令牌（失败不阻塞本地登出）
      if (rt) {
        api.post('/auth/logout', { refresh_token: rt }).catch(() => {})
      }
    }
  }
})
