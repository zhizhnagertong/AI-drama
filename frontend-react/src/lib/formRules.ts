/**
 * 表单校验规则：与后端 schemas.py 同源（同一正则、同一文案）。
 * 移植自 Vue 版 src/composables/useFormRules.js。
 * 说明：antd 的 Rule 结构天然兼容 required/pattern/message，
 * 因此这里只保留声明式规则，不再包装成 element-plus 的 validator 回调。
 */

// 注册用户名：3-20 位字母/数字
export const REGISTER_USERNAME_PATTERN = /^[A-Za-z0-9]{3,20}$/
// 登录用户名：3-20 位，允许中文/下划线（兼容历史账号）
export const LOGIN_USERNAME_PATTERN = /^[A-Za-z0-9_\u4e00-\u9fa5]{3,20}$/
// 密码：8-20 位，含大写 + 小写 + 数字，不含空格
export const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)\S{8,20}$/
// 邮箱（选填）
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export interface SimpleRule {
  required?: boolean
  pattern?: RegExp
  message?: string
}

export type RulesMap = Record<string, SimpleRule[]>

export function loginRules(): RulesMap {
  return {
    username: [
      { required: true, message: '请输入用户名' },
      { pattern: LOGIN_USERNAME_PATTERN, message: '3-20 位字母、数字、下划线或中文' }
    ],
    // 登录不校验密码强度，强度只在注册 / 重置时校验
    password: [{ required: true, message: '请输入密码' }]
  }
}

export function registerRules(): RulesMap {
  return {
    username: [
      { required: true, message: '请输入用户名' },
      { pattern: REGISTER_USERNAME_PATTERN, message: '3-20 位字母或数字' }
    ],
    password: [
      { required: true, message: '请输入密码' },
      {
        pattern: PASSWORD_PATTERN,
        message: '8-20 位，须含大写、小写字母和数字，不含空格'
      }
    ],
    email: [{ pattern: EMAIL_PATTERN, message: '邮箱格式不正确' }]
  }
}

/** 密码强度：0-4 分（长度 / 大小写 / 数字 / 符号） */
export function passwordStrength(pwd: string): { score: number; label: string; color: string } {
  if (!pwd) return { score: 0, label: '', color: 'var(--text-tertiary)' }
  let score = 0
  if (pwd.length >= 8) score++
  if (pwd.length >= 12) score++
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
  if (/\d/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++
  const levels = [
    { label: '太弱', color: 'var(--danger)' },
    { label: '太弱', color: 'var(--danger)' },
    { label: '一般', color: 'var(--warning)' },
    { label: '较强', color: 'var(--primary)' },
    { label: '强', color: 'var(--success)' },
    { label: '很强', color: 'var(--success)' }
  ]
  return { score, ...levels[score] }
}