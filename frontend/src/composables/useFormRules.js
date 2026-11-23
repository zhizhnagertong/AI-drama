/**
 * 表单校验规则：与后端 schemas.py 同源（同一正则、同一文案）。
 */

// 注册用户名：3-20 位字母/数字
export const REGISTER_USERNAME_PATTERN = /^[A-Za-z0-9]{3,20}$/
// 登录用户名：3-20 位，允许中文/下划线（兼容历史账号）
export const LOGIN_USERNAME_PATTERN = /^[A-Za-z0-9_\u4e00-\u9fa5]{3,20}$/
// 密码：8-20 位，含大写 + 小写 + 数字，不含空格
export const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)\S{8,20}$/
// 邮箱（选填）
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** 密码强度：0-4 分（长度/小写/大写/数字/符号） */
export function passwordStrength(pwd) {
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
  const l = levels[score]
  return { score, ...l }
}

const usernameRule = (pattern, msg) => [
  { required: true, message: '请输入用户名', trigger: 'blur' },
  { pattern, message: msg, trigger: 'blur' }
]

const passwordRule = [
  { required: true, message: '请输入密码', trigger: 'blur' },
  { pattern: PASSWORD_PATTERN, message: '8-20 位，须含大写、小写字母和数字，不含空格', trigger: 'blur' }
]

export function loginRules() {
  return {
    username: usernameRule(LOGIN_USERNAME_PATTERN, '3-20 位字母、数字、下划线或中文'),
    password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
  }
}

export function registerRules(getPassword) {
  return {
    username: usernameRule(REGISTER_USERNAME_PATTERN, '3-20 位字母或数字'),
    password: passwordRule,
    confirm_password: [
      { required: true, message: '请再次输入密码', trigger: 'blur' },
      {
        validator: (_r, v, cb) => {
          if (!v) return cb()
          if (getPassword && v !== getPassword()) cb(new Error('两次输入的密码不一致'))
          else cb()
        },
        trigger: 'blur'
      }
    ],
    email: [
      {
        validator: (_r, v, cb) => {
          if (v && !EMAIL_PATTERN.test(v)) cb(new Error('邮箱格式不正确'))
          else cb()
        },
        trigger: 'blur'
      }
    ],
    agree_terms: [
      {
        validator: (_r, v, cb) => {
          if (!v) cb(new Error('请先阅读并同意服务条款'))
          else cb()
        },
        trigger: 'change'
      }
    ]
  }
}

/** 重置密码表单规则（第三步） */
export function resetRules(getPassword) {
  return {
    new_password: passwordRule,
    confirm_password: [
      { required: true, message: '请再次输入新密码', trigger: 'blur' },
      {
        validator: (_r, v, cb) => {
          if (v !== getPassword()) cb(new Error('两次输入的密码不一致'))
          else cb()
        },
        trigger: 'blur'
      }
    ]
  }
}
