/**
 * 会话状态：模块级令牌真源 + 设备指纹 + 会话失效广播。
 *
 * 独立成文件的原因：api/index.js 需要读取令牌，stores/auth.js 需要写入令牌，
 * 而 router 守卫也需要读取令牌。若都放在 store 里会形成
 * request → store → request 的循环依赖，这里以纯模块承载共享状态。
 */
import { ref } from 'vue'

const ACCESS_KEY = 'auth.access'
const REFRESH_KEY = 'auth.refresh'
const USER_KEY = 'auth.user'
const DEVICE_KEY = 'auth.device'
const REMEMBER_KEY = 'auth.remember'

export const accessToken = ref('')
export const refreshToken = ref('')
export const currentUser = ref(null)

/** 过期时间（毫秒时间戳），用于启动时判断本地会话是否已失效 */
export const accessExpiresAt = ref(0)
export const refreshExpiresAt = ref(0)

/**
 * 会话代际号：每次 clearSession 自增。
 * 用于作废"登出/失效前发出、登出后才返回"的后台刷新结果——
 * 否则它会把新令牌写回 storage，导致退出登录后又自动恢复登录态。
 */
export const sessionEpoch = ref(0)

const listeners = new Set()

/** 订阅会话失效事件，返回取消订阅函数 */
export function onSessionExpired(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** 广播会话失效（令牌彻底不可用时调用） */
export function emitSessionExpired(reason = '') {
  listeners.forEach((fn) => {
    try {
      fn(reason)
    } catch {
      /* 单个监听器异常不影响其他 */
    }
  })
}

/** 设备指纹：首次生成后持久化，用于 refresh_tokens 表标识设备 */
export function deviceId() {
  try {
    const exist = localStorage.getItem(DEVICE_KEY)
    if (exist) return exist
  } catch {
    /* ignore */
  }
  const id =
    'dev_' +
    Math.random().toString(36).slice(2, 10) +
    Date.now().toString(36)
  try {
    localStorage.setItem(DEVICE_KEY, id)
  } catch {
    /* ignore */
  }
  return id
}

function storageFor(remember) {
  return remember ? localStorage : sessionStorage
}

/**
 * 写入会话。
 * remember=true → localStorage（7 天）；false → sessionStorage（关浏览器失效）。
 */
export function persistSession({ access, refresh, user, expiresIn, refreshExpiresIn, remember }) {
  const store = storageFor(remember)
  const other = remember ? sessionStorage : localStorage
  try {
    store.setItem(ACCESS_KEY, access)
    store.setItem(REFRESH_KEY, refresh)
    store.setItem(REMEMBER_KEY, remember ? '1' : '0')
    if (user) store.setItem(USER_KEY, JSON.stringify(user))
    const now = Date.now()
    if (expiresIn) store.setItem(`${ACCESS_KEY}.exp`, String(now + expiresIn * 1000))
    if (refreshExpiresIn) store.setItem(`${REFRESH_KEY}.exp`, String(now + refreshExpiresIn * 1000))
    // 切换记住我策略时清掉另一侧的会话，避免双份登录态
    // 注意：必须连过期时间键一起清，否则 restoreSession 会读到旧会话残留的
    // auth.*.exp，把有效会话误判为已过期（刷新页面即被强制登出）
    other.removeItem(ACCESS_KEY)
    other.removeItem(REFRESH_KEY)
    other.removeItem(USER_KEY)
    other.removeItem(REMEMBER_KEY)
    other.removeItem(`${ACCESS_KEY}.exp`)
    other.removeItem(`${REFRESH_KEY}.exp`)
  } catch {
    /* 隐私模式下 localStorage 可能不可写，仅保留内存态 */
  }
  accessToken.value = access
  refreshToken.value = refresh
  if (user) currentUser.value = user
  if (expiresIn) accessExpiresAt.value = Date.now() + expiresIn * 1000
  if (refreshExpiresIn) refreshExpiresAt.value = Date.now() + refreshExpiresIn * 1000
}

/** 仅更新令牌（无感刷新后调用），沿用当前存储策略 */
export function updateTokens({ access, refresh, expiresIn, refreshExpiresIn }) {
  const remember = readRemember()
  const store = storageFor(remember)
  const now = Date.now()
  try {
    if (access) store.setItem(ACCESS_KEY, access)
    if (refresh) store.setItem(REFRESH_KEY, refresh)
    if (expiresIn) store.setItem(`${ACCESS_KEY}.exp`, String(now + expiresIn * 1000))
    // 服务端每次刷新都会轮换 refresh 并延长有效期，这里必须同步更新过期时间，
    // 否则续期后仍按最初登录时的 7 天判死，到期被强制登出
    if (refreshExpiresIn) store.setItem(`${REFRESH_KEY}.exp`, String(now + refreshExpiresIn * 1000))
  } catch {
    /* ignore */
  }
  if (access) accessToken.value = access
  if (refresh) refreshToken.value = refresh
  if (expiresIn) accessExpiresAt.value = now + expiresIn * 1000
  if (refreshExpiresIn) refreshExpiresAt.value = now + refreshExpiresIn * 1000
}

export function setUser(user) {
  currentUser.value = user
  try {
    storageFor(readRemember()).setItem(USER_KEY, JSON.stringify(user))
  } catch {
    /* ignore */
  }
}

function readRemember() {
  try {
    return localStorage.getItem(REMEMBER_KEY) === '1' || sessionStorage.getItem(REMEMBER_KEY) === '1'
  } catch {
    return false
  }
}

/** 启动时恢复会话（刷新页面保持登录态） */
export function restoreSession() {
  // 旧版单令牌键（token/user）已废弃：静默清除，避免与新会话键混淆
  try {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('user')
  } catch {
    /* ignore */
  }
  let access = ''
  let refresh = ''
  let user = null
  let accessExp = 0
  let refreshExp = 0
  // 只在真正存放令牌的那个 store 里读它的过期时间：
  // 若两边各取“第一个非 0 值”，会读到上一次登录策略残留的旧 exp
  let source = null
  for (const store of [localStorage, sessionStorage]) {
    try {
      if (!refresh) {
        const candidate = store.getItem(REFRESH_KEY) || ''
        if (candidate) {
          refresh = candidate
          source = store
        }
      }
    } catch {
      /* ignore */
    }
  }
  if (source) {
    try {
      access = source.getItem(ACCESS_KEY) || ''
      const raw = source.getItem(USER_KEY)
      user = raw ? JSON.parse(raw) : null
      accessExp = Number(source.getItem(`${ACCESS_KEY}.exp`) || 0)
      refreshExp = Number(source.getItem(`${REFRESH_KEY}.exp`) || 0)
    } catch {
      /* ignore */
    }
  }
  accessToken.value = access
  refreshToken.value = refresh
  currentUser.value = user
  accessExpiresAt.value = accessExp
  refreshExpiresAt.value = refreshExp
  // refresh 已过期则视为无会话
  if (refresh && refreshExp && refreshExp <= Date.now()) {
    clearSession()
    return false
  }
  return !!refresh
}

export function clearSession() {
  sessionEpoch.value += 1
  accessToken.value = ''
  refreshToken.value = ''
  currentUser.value = null
  accessExpiresAt.value = 0
  refreshExpiresAt.value = 0
  for (const store of [localStorage, sessionStorage]) {
    try {
      store.removeItem(ACCESS_KEY)
      store.removeItem(REFRESH_KEY)
      store.removeItem(USER_KEY)
      store.removeItem(REMEMBER_KEY)
      store.removeItem(`${ACCESS_KEY}.exp`)
      store.removeItem(`${REFRESH_KEY}.exp`)
    } catch {
      /* ignore */
    }
  }
}

export function isRefreshExpired() {
  return !!refreshToken.value && !!refreshExpiresAt.value && refreshExpiresAt.value <= Date.now()
}
