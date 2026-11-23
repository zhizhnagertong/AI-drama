/** 忘记密码三步弹窗：校验用户 → 输入验证码（60s 重发倒计时）→ 重置密码。 */
import { KeyOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Form, Input, Modal } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'

import type { ApiError } from '@/api/client'
import { authApi } from '@/api/auth'
import { toast } from '@/lib/feedback'
import { PASSWORD_PATTERN, passwordStrength } from '@/lib/formRules'

interface ForgetPasswordModalProps {
  open: boolean
  onClose: () => void
  onDone: (username: string) => void
}

interface PasswordValues {
  new_password: string
  confirm_password: string
}

const STEP_NAMES = ['验证身份', '输入验证码', '重置密码']

export function ForgetPasswordModal({ open, onClose, onDone }: ForgetPasswordModalProps) {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [username, setUsername] = useState('')
  const [code, setCode] = useState('')
  const [maskedContact, setMaskedContact] = useState<string | null>(null)
  const [codeHint, setCodeHint] = useState('')

  const [countdown, setCountdown] = useState(0)
  const timerRef = useRef<number | null>(null)

  const [form] = Form.useForm<PasswordValues>()
  const newPassword = Form.useWatch('new_password', form) || ''
  const strength = passwordStrength(newPassword)
  const strengthWidth = `${Math.min(strength.score, 4) * 25}%`

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startCountdown = useCallback(
    (seconds: number) => {
      setCountdown(seconds)
      clearTimer()
      timerRef.current = window.setInterval(() => {
        setCountdown((v) => {
          if (v <= 1) {
            clearTimer()
            return 0
          }
          return v - 1
        })
      }, 1000)
    },
    [clearTimer]
  )

  // 关闭时完全重置（替代 Vue 的 watch(visible)）
  useEffect(() => {
    if (!open) {
      setStep(1)
      setError('')
      setCodeHint('')
      setCountdown(0)
      clearTimer()
      setUsername('')
      setCode('')
      setMaskedContact(null)
      form.resetFields()
    }
  }, [open, clearTimer, form])

  useEffect(() => clearTimer, [clearTimer])

  /* -------- Step 1：校验用户 -------- */
  async function nextFromUser() {
    setError('')
    const name = username.trim()
    if (!name) {
      setError('请输入用户名')
      return
    }
    setLoading(true)
    try {
      const data = await authApi.verifyUser(name)
      if (!data?.exists) {
        setError('用户不存在，请检查用户名')
        return
      }
      setMaskedContact(data.masked_contact ?? null)
      await doSendCode(true)
      setStep(2)
    } catch (raw) {
      setError((raw as ApiError)?.friendlyMessage || '校验失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  /* -------- Step 2：验证码 -------- */
  async function doSendCode(silent = false) {
    setError('')
    try {
      const data = await authApi.sendCode(username.trim())
      setCodeHint(data?.code_hint || '')
      startCountdown(data?.resend_interval || 60)
      if (!silent) toast.success('验证码已发送')
    } catch (raw) {
      const err = raw as ApiError
      const msg = err?.friendlyMessage || '发送失败'
      if (err?.bizCode === 'RESEND_TOO_FAST') toast.warning(msg)
      else setError(msg)
    }
  }

  async function nextFromCode() {
    setError('')
    const value = code.trim()
    if (!/^\d{6}$/.test(value)) {
      setError('请输入 6 位数字验证码')
      return
    }
    setLoading(true)
    try {
      await authApi.verifyCode(username.trim(), value)
      setStep(3)
    } catch (raw) {
      setError((raw as ApiError)?.friendlyMessage || '验证码错误')
    } finally {
      setLoading(false)
    }
  }

  /* -------- Step 3：重置密码 -------- */
  async function doReset() {
    setError('')
    let values: PasswordValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    if (!PASSWORD_PATTERN.test(values.new_password)) {
      setError('密码须为 8-20 位，包含大写、小写字母和数字，不含空格')
      return
    }
    setLoading(true)
    try {
      await authApi.resetPassword({
        username: username.trim(),
        code: code.trim(),
        new_password: values.new_password,
        confirm_password: values.confirm_password
      })
      toast.success('密码重置成功，请使用新密码登录')
      onClose()
      onDone(username.trim())
    } catch (raw) {
      const err = raw as ApiError
      const msg = err?.friendlyMessage || '重置失败'
      setError(msg)
      // 验证码过期则退回第 2 步重新获取
      if (err?.bizCode === 'CODE_EXPIRED') setStep(2)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title="找回密码"
      open={open}
      onCancel={onClose}
      footer={null}
      width={440}
      centered
      maskClosable={false}
      className="forget-dialog"
    >
      {/* 步骤指示器 */}
      <div className="fp-steps">
        {STEP_NAMES.map((name, i) => {
          const idx = i + 1
          return (
            <div
              key={name}
              className={`fp-step${step >= idx ? ' active' : ''}${step === idx ? ' current' : ''}`}
            >
              <span className="fp-dot">{idx}</span>
              <span className="fp-name">{name}</span>
              {idx < 3 && <span className="fp-line" />}
            </div>
          )
        })}
      </div>

      {step === 1 && (
        <div className="fp-pane">
          <p className="fp-hint">输入你的用户名，我们将向你绑定的邮箱发送验证码。</p>
          <Input
            size="large"
            value={username}
            prefix={<UserOutlined />}
            placeholder="请输入用户名"
            onChange={(e) => setUsername(e.target.value)}
            onPressEnter={nextFromUser}
          />
          {error && <p className="fp-error">{error}</p>}
          <Button
            className="fp-submit"
            type="primary"
            shape="round"
            block
            loading={loading}
            onClick={nextFromUser}
          >
            下一步
          </Button>
        </div>
      )}

      {step === 2 && (
        <div className="fp-pane">
          <p className="fp-hint">
            验证码已发送至
            <strong>{maskedContact || '你的邮箱（开发模式直接回显）'}</strong>
          </p>
          {codeHint && (
            <p className="fp-dev-hint">
              开发模式验证码：<code>{codeHint}</code>
            </p>
          )}
          <Input
            size="large"
            value={code}
            maxLength={6}
            prefix={<KeyOutlined />}
            placeholder="6 位数字验证码"
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={nextFromCode}
          />
          {error && <p className="fp-error">{error}</p>}
          <div className="fp-code-row">
            <Button
              type="link"
              disabled={countdown > 0 || loading}
              onClick={() => void doSendCode()}
            >
              {countdown > 0 ? `${countdown}s 后重发` : '重新发送'}
            </Button>
            <Button type="link" onClick={() => setStep(1)}>
              返回上一步
            </Button>
          </div>
          <Button
            className="fp-submit"
            type="primary"
            shape="round"
            block
            loading={loading}
            onClick={nextFromCode}
          >
            下一步
          </Button>
        </div>
      )}

      {step === 3 && (
        <div className="fp-pane">
          <Form form={form} layout="vertical" requiredMark={false}>
            <Form.Item
              name="new_password"
              label="新密码"
              rules={[
                { required: true, message: '请输入新密码' },
                { pattern: PASSWORD_PATTERN, message: '8-20 位，须含大写、小写字母和数字' }
              ]}
            >
              <Input.Password size="large" prefix={<LockOutlined />} placeholder="8-20 位，含大小写字母和数字" />
            </Form.Item>

            {newPassword && (
              <div className="fp-strength">
                <div className="fp-strength-track">
                  <div
                    className="fp-strength-bar"
                    style={{ width: strengthWidth, background: strength.color }}
                  />
                </div>
                <span className="fp-strength-label" style={{ color: strength.color }}>
                  {strength.label}
                </span>
              </div>
            )}

            <Form.Item
              name="confirm_password"
              label="确认新密码"
              rules={[
                { required: true, message: '请再次输入新密码' },
                ({ getFieldValue }) => ({
                  validator(_rule, value: string) {
                    if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                    return Promise.reject(new Error('两次输入的密码不一致'))
                  }
                })
              ]}
            >
              <Input.Password
                size="large"
                prefix={<LockOutlined />}
                placeholder="请再次输入新密码"
                onPressEnter={doReset}
              />
            </Form.Item>
          </Form>
          {error && <p className="fp-error">{error}</p>}
          <Button
            className="fp-submit"
            type="primary"
            shape="round"
            block
            loading={loading}
            onClick={doReset}
          >
            重置密码
          </Button>
        </div>
      )}
    </Modal>
  )
}