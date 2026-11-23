/** 登录表单：字段级错误回显 + 记住我 + 锁定/凭证错误提示。 */
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Checkbox, Form, Input } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import type { ApiError } from '@/api/client'
import { toast } from '@/lib/feedback'
import { loginRules } from '@/lib/formRules'
import { useAuthStore } from '@/store/auth'

interface LoginFormValues {
  username: string
  password: string
  remember: boolean
}

interface LoginFormProps {
  prefill?: string
  onForget: () => void
  onSwitch: () => void
}

export function LoginForm({ prefill = '', onForget, onSwitch }: LoginFormProps) {
  const [form] = Form.useForm<LoginFormValues>()
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const login = useAuthStore((s) => s.login)

  // 注册成功 / 找回密码完成后回填用户名
  useEffect(() => {
    if (prefill) form.setFieldValue('username', prefill)
  }, [prefill, form])

  async function submit() {
    let values: LoginFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setLoading(true)
    try {
      await login(values.username.trim(), values.password, !!values.remember)
      toast.success('欢迎回来！')
      const redirect = searchParams.get('redirect')
      navigate(redirect || '/', { replace: true })
    } catch (raw) {
      const err = raw as ApiError
      const msg = err?.friendlyMessage || '登录失败，请重试'

      if (err?.bizCode === 'ACCOUNT_LOCKED') {
        toast.warning(msg, 5)
      } else if (err?.bizCode === 'VALIDATION_ERROR' && err.fieldErrors) {
        // 后端字段级错误直接回显到对应 Form.Item
        const fieldKeys: (keyof LoginFormValues)[] = ['username', 'password']
        const fields = fieldKeys
          .filter((k) => err.fieldErrors?.[k])
          .map((k) => ({ name: k, errors: [err.fieldErrors![k]] }))
        if (fields.length) {
          form.setFields(fields)
        } else {
          toast.error(msg)
        }
      } else {
        form.setFields([{ name: 'password', errors: [msg] }])
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form<LoginFormValues>
      form={form}
      layout="vertical"
      requiredMark={false}
      initialValues={{ username: prefill, password: '', remember: false }}
      onFinish={submit}
      className="login-form"
    >
      <Form.Item name="username" label="用户名" rules={loginRules().username}>
        <Input
          size="large"
          prefix={<UserOutlined />}
          placeholder="请输入用户名"
          autoComplete="username"
          spellCheck={false}
        />
      </Form.Item>

      <Form.Item name="password" label="密码" rules={loginRules().password}>
        <Input.Password
          size="large"
          prefix={<LockOutlined />}
          placeholder="请输入密码"
          autoComplete="current-password"
        />
      </Form.Item>

      <div className="row">
        <Form.Item name="remember" valuePropName="checked" noStyle>
          <Checkbox>记住我</Checkbox>
        </Form.Item>
        <button type="button" className="link-btn" onClick={onForget}>
          忘记密码？
        </button>
      </div>

      <Button
        className="submit"
        type="primary"
        size="large"
        block
        loading={loading}
        disabled={loading}
        htmlType="submit"
      >
        登录
      </Button>

      <p className="switch-tip">
        还没有账号？
        <button type="button" className="link-btn" onClick={onSwitch}>
          立即注册
        </button>
      </p>
    </Form>
  )
}