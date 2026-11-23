import api, { unwrap } from '@/api/client'
import type { LoginResult } from '@/types'

export interface RegisterPayload {
  username: string
  password: string
  confirm_password?: string
  email?: string
  /** 后端强校验：未同意条款返回 422 TERMS_NOT_AGREED */
  agree_terms: boolean
}

export interface VerifyUserResult {
  exists: boolean
  channel?: string | null
  masked_contact?: string | null
}

export interface SendCodeResult {
  sent: boolean
  channel: string
  expires_in: number
  resend_interval: number
  /** 仅 channel=none 的历史账号会回显（无邮箱可用） */
  code_hint?: string | null
}

export interface ResetPasswordPayload {
  username: string
  code: string
  new_password: string
  confirm_password: string
}

export const authApi = {
  login(username: string, password: string, remember: boolean): Promise<LoginResult> {
    return api
      .post('/auth/login', { username, password, remember })
      .then((res) => unwrap<LoginResult>(res))
  },

  register(payload: RegisterPayload): Promise<unknown> {
    return api.post('/auth/register', payload).then((res) => unwrap<unknown>(res))
  },

  logout(refreshToken: string): Promise<unknown> {
    return api.post('/auth/logout', { refresh_token: refreshToken }).then((res) => res.data)
  },

  /* ---------------- 找回密码三步 ---------------- */

  verifyUser(username: string): Promise<VerifyUserResult> {
    return api
      .post('/auth/verify-user', { username })
      .then((res) => unwrap<VerifyUserResult>(res))
  },

  sendCode(username: string): Promise<SendCodeResult> {
    return api
      .post('/auth/password/send-code', { username })
      .then((res) => unwrap<SendCodeResult>(res))
  },

  verifyCode(username: string, code: string): Promise<unknown> {
    return api
      .post('/auth/password/verify-code', { username, code })
      .then((res) => unwrap<unknown>(res))
  },

  resetPassword(payload: ResetPasswordPayload): Promise<unknown> {
    return api.post('/auth/password/reset', payload).then((res) => unwrap<unknown>(res))
  }
}