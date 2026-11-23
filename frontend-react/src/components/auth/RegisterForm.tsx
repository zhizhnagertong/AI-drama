/** 注册表单：用户名/密码/确认密码/邮箱/条款勾选 + 密码强度条。
 * 注册成功后不自动登录：提示并回填用户名切回登录（对齐注册业务流程图）。 */
import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Checkbox, Form, Input } from 'antd'
import type { Rule } from 'antd/es/form'
import { useState } from 'react'

import type { ApiError } from '@/api/client'
import type { RegisterPayload } from '@/api/auth'
import { toast } from '@/lib/feedback'
import {
  PASSWORD_PATTERN,
  REGISTER_USERNAME_PATTERN,
  passwordStrength
} from '@/lib/formRules'
import { useAuthStore } from '@/store/auth'

interface RegisterFormValues {
  username: string
  password: string
  confirm_password: string
  email?: string
  agree_terms: boolean
}

interface RegisterFormProps {
  onSwitch: () => void
  /** 注册成功回填用户名，由父组件切回登录 Tab */
  onRegistered: (username: string) => void
}

export function RegisterForm({ onSwitch, onRegistered }: RegisterFormProps) {
  const [form] = Form.useForm<RegisterFormValues>()
  const [loading, setLoading] = useState(false)
  const register = useAuthStore((s) => s.register)

  // 密码强度条：相当于 Vue 的 computed(() => passwordStrength(form.password))
  const password = Form.useWatch('password', form) || ''
  const strength = passwordStrength(password)
  const strengthWidth = `${Math.min(strength.score, 4) * 25}%`

  const rules: Record<string, Rule[]> = {
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
    confirm_password: [
      { required: true, message: '请再次输入密码' },
      ({ getFieldValue }) => ({
        validator(_rule, value: string) {
          if (!value || getFieldValue('password') === value) return Promise.resolve()
          return Promise.reject(new Error('两次输入的密码不一致'))
        }
      })
    ],
    email: [{ type: 'email', message: '邮箱格式不正确' }],
    agree_terms: [
      {
        validator: (_rule, value: boolean) =>
          value ? Promise.resolve() : Promise.reject(new Error('请先阅读并同意服务条款'))
      }
    ]
  }

  async function submit(values: RegisterFormValues) {
    setLoading(true)
    try {
      const payload: RegisterPayload = {
        username: values.username.trim(),
        password: values.password,
        confirm_password: values.confirm_password,
        email: values.email?.trim() || undefined,
        agree_terms: true
      }
      const data = (await register(payload)) as { username?: string } | undefined
      toast.success('注册成功，请登录')
      onRegistered(data?.username || values.username.trim())
    } catch (raw) {
      const err = raw as ApiError
      const msg = err?.friendlyMessage || '注册失败，请重试'

      // 业务码 → 字段级回显（与原版一致）
      if (err?.bizCode === 'USERNAME_TAKEN') {
        form.setFields([{ name: 'username', errors: [msg] }])
      } else if (err?.bizCode === 'EMAIL_TAKEN') {
        form.setFields([{ name: 'email', errors: [msg] }])
      } else if (err?.bizCode === 'TERMS_NOT_AGREED') {
        form.setFields([{ name: 'agree_terms', errors: [msg] }])
      } else if (err?.bizCode === 'VALIDATION_ERROR' && err.fieldErrors) {
        const keys: (keyof RegisterFormValues)[] = [
          'username',
          'password',
          'confirm_password',
          'email'
        ]
        const fields = keys
          .filter((k) => err.fieldErrors?.[k])
          .map((k) => ({ name: k, errors: [err.fieldErrors![k]] }))
        if (fields.length) form.setFields(fields)
        else toast.error(msg)
      } else {
        toast.error(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form<RegisterFormValues>
      form={form}
      layout="vertical"
      requiredMark={false}
      initialValues={{ agree_terms: false }}
      onFinish={submit}
      className="register-form"
    >
      <Form.Item name="username" label="用户名" rules={rules.username}>
        <Input
          size="large"
          prefix={<UserOutlined />}
          placeholder="3-20 位字母或数字"
          autoComplete="username"
          spellCheck={false}
        />
      </Form.Item>

      <Form.Item name="password" label="密码" rules={rules.password}>
        <Input.Password
          size="large"
          prefix={<LockOutlined />}
          placeholder="8-20 位，含大小写字母和数字"
          autoComplete="new-password"
        />
      </Form.Item>

      {password && (
        <div className="strength">
          <div className="strength-track">
            <div
              className="strength-bar"
              style={{ width: strengthWidth, background: strength.color }}
            />
          </div>
          <span className="strength-label" style={{ color: strength.color }}>
            {strength.label}
          </span>
        </div>
      )}

      <Form.Item name="confirm_password" label="确认密码" rules={rules.confirm_password}>
        <Input.Password
          size="large"
          prefix={<LockOutlined />}
          placeholder="请再次输入密码"
          autoComplete="new-password"
        />
      </Form.Item>

      <Form.Item name="email" label="邮箱（选填，用于找回密码）" rules={rules.email}>
        <Input
          size="large"
          prefix={<MailOutlined />}
          placeholder="name@example.com"
          autoComplete="email"
          spellCheck={false}
        />
      </Form.Item>

      <Form.Item name="agree_terms" valuePropName="checked" rules={rules.agree_terms}>
        <Checkbox>
          <span className="terms-text">我已阅读并同意</span>
        </Checkbox>
      </Form.Item>
      <p className="terms-link-row">
        <span className="terms-link">《AI 生成内容使用规范》</span>
      </p>

      <Button
        className="submit"
        type="primary"
        size="large"
        block
        loading={loading}
        disabled={loading}
        htmlType="submit"
      >
        注册
      </Button>

      <p className="switch-tip">
        已有账号？
        <button type="button" className="link-btn" onClick={onSwitch}>
          返回登录
        </button>
      </p>
    </Form>
  )
}