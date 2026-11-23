/** 我的：资料头部 + 我的作品 + 账号设置（对应 Vue 版 views/Mine.vue）。 */
import { Button, Empty, Form, Input, Modal, Switch } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import api, { unwrap } from '@/api/client'
import type { ApiError } from '@/api/client'
import { ProjectCard } from '@/components/ProjectCard'
import { confirmDialog, toast } from '@/lib/feedback'
import { displayNameOf, firstChar } from '@/lib/format'
import { PASSWORD_PATTERN } from '@/lib/formRules'
import { projectsApi } from '@/api/projects'
import { useSessionStore } from '@/store/session'
import { useThemeStore } from '@/store/theme'
import type { Project, User } from '@/types'

const MODELS = [
  { name: 'agnes-2.5-flash', usage: '剧本 / 分镜脚本等文本创作' },
  { name: 'agnes-image-2.1-flash', usage: '分镜与角色参考图生成' },
  { name: 'agnes-video-2.5-flash', usage: '图生视频动效' }
]

interface ProfileValues {
  nickname: string
}

interface PasswordValues {
  old_password: string
  new_password: string
  confirm: string
}

export function Mine() {
  const navigate = useNavigate()
  const user = useSessionStore((s) => s.user)
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggle)

  const [works, setWorks] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)

  /* ---------------- 编辑资料 ---------------- */
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileForm] = Form.useForm<ProfileValues>()

  function openProfile() {
    profileForm.setFieldsValue({ nickname: user?.nickname || user?.username || '' })
    setProfileOpen(true)
  }

  async function saveProfile() {
    let values: ProfileValues
    try {
      values = await profileForm.validateFields()
    } catch {
      return
    }
    if (!values.nickname.trim()) {
      toast.warning('昵称不能为空')
      return
    }
    setProfileSaving(true)
    try {
      const data = unwrap<User>(await api.put('/auth/me', { nickname: values.nickname.trim() }))
      useSessionStore.getState().setUser(data)
      setProfileOpen(false)
      toast.success('资料已更新')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setProfileSaving(false)
    }
  }

  /* ---------------- 修改密码 ---------------- */
  const [pwdOpen, setPwdOpen] = useState(false)
  const [pwdSaving, setPwdSaving] = useState(false)
  const [pwdForm] = Form.useForm<PasswordValues>()

  function openPassword() {
    pwdForm.resetFields()
    setPwdOpen(true)
  }

  async function savePassword() {
    let values: PasswordValues
    try {
      values = await pwdForm.validateFields()
    } catch {
      return
    }
    setPwdSaving(true)
    try {
      await api.put('/auth/me/password', {
        old_password: values.old_password,
        new_password: values.new_password
      })
      setPwdOpen(false)
      toast.success('密码已更新')
    } catch (raw) {
      // OLD_PASSWORD_WRONG 回显到原密码字段
      const err = raw as ApiError
      if (err?.bizCode === 'OLD_PASSWORD_WRONG') {
        pwdForm.setFields([{ name: 'old_password', errors: [err.friendlyMessage || '原密码错误'] }])
      }
    } finally {
      setPwdSaving(false)
    }
  }

  /* ---------------- 数据加载 ---------------- */
  useEffect(() => {
    let alive = true
    setLoading(true)
    projectsApi
      .list({ page: 1, page_size: 100 })
      .then((list) => {
        if (alive) setWorks(list)
      })
      .catch(() => {
        /* 拦截器已提示 */
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const stats = useMemo(
    () => ({
      total: works.length,
      producing: works.filter((w) => w.status === 'producing').length,
      completed: works.filter((w) => w.status === 'completed').length
    }),
    [works]
  )

  async function clearCache() {
    const ok = await confirmDialog({
      title: '清除本地缓存',
      content: '将清除本地缓存的主题等偏好数据（不影响登录状态与云端作品），是否继续？',
      okText: '清除',
      cancelText: '取消'
    })
    if (!ok) return
    // 保留会话键（auth.* 前缀）与主题键
    for (const store of [window.localStorage, window.sessionStorage]) {
      try {
        const keep: Record<string, string> = {}
        for (let i = 0; i < store.length; i++) {
          const k = store.key(i)
          if (k && (k.startsWith('auth.') || k === 'theme')) keep[k] = store.getItem(k) as string
        }
        store.clear()
        for (const [k, v] of Object.entries(keep)) store.setItem(k, v)
      } catch {
        /* ignore */
      }
    }
    toast.success('本地缓存已清除')
  }

  return (
    <div className="g-page">
      <div className="mine-header">
        <div className="mine-avatar">{firstChar(displayNameOf(user))}</div>
        <div className="mine-info">
          <h1>{displayNameOf(user)}</h1>
          <p>@{user?.username || '-'}</p>
          <div className="mine-stats">
            <div className="mine-stat">
              <b className="num">{stats.total}</b>
              <span>作品</span>
            </div>
            <div className="mine-stat">
              <b className="num">{stats.producing}</b>
              <span>进行中</span>
            </div>
            <div className="mine-stat">
              <b className="num">{stats.completed}</b>
              <span>已完成</span>
            </div>
          </div>
        </div>
        <Button className="edit-profile" shape="round" onClick={openProfile}>
          编辑资料
        </Button>
      </div>

      <h2 className="g-section-title">我的作品</h2>
      {loading ? (
        <div className="mine-loading">加载中…</div>
      ) : works.length ? (
        <div className="mine-grid">
          {works.map((p, i) => (
            <ProjectCard
              key={p.id}
              project={p}
              delay={Math.min(i + 1, 6)}
              onDeleted={(id) => setWorks((prev) => prev.filter((x) => x.id !== id))}
            />
          ))}
        </div>
      ) : (
        <div className="g-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="还没有作品，去「创作」页开启第一部漫剧吧"
          />
        </div>
      )}

      <h2 className="g-section-title settings-title">账号设置</h2>

      <div className="setting-card">
        <span className="setting-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        </span>
        <div className="setting-text">
          <b>深色模式</b>
        </div>
        <Switch
          checked={theme === 'dark'}
          checkedChildren="深色"
          unCheckedChildren="浅色"
          aria-label="切换深色/浅色主题"
          onChange={toggleTheme}
        />
      </div>

      <div className="setting-card setting-card--models">
        <span className="setting-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="4" y="4" width="16" height="16" rx="2" />
            <rect x="9" y="9" width="6" height="6" />
            <line x1="9" y1="1" x2="9" y2="4" />
            <line x1="15" y1="1" x2="15" y2="4" />
            <line x1="9" y1="20" x2="9" y2="23" />
            <line x1="15" y1="20" x2="15" y2="23" />
            <line x1="20" y1="9" x2="23" y2="9" />
            <line x1="20" y1="14" x2="23" y2="14" />
            <line x1="1" y1="9" x2="4" y2="9" />
            <line x1="1" y1="14" x2="4" y2="14" />
          </svg>
        </span>
        <div className="setting-text">
          <b>AI 模型信息（只读）</b>
          <span>当前平台使用的生成模型</span>
        </div>
        <div className="model-list">
          {MODELS.map((m) => (
            <div key={m.name} className="model">
              <span className="mname mono">{m.name}</span>
              <span className="musage">{m.usage}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="setting-card">
        <span className="setting-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="11" width="18" height="11" rx="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </span>
        <div className="setting-text">
          <b>修改密码</b>
          <span>定期更新密码更安全</span>
        </div>
        <Button shape="round" size="small" onClick={openPassword}>
          修改密码
        </Button>
      </div>

      <div
        className="setting-card setting-card--link"
        role="button"
        tabIndex={0}
        onClick={() => navigate('/styles')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') navigate('/styles')
        }}
      >
        <span className="setting-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22a10 10 0 1 1 10-10c0 1.5-1 2-2 2h-2a2 2 0 0 0-2 2c0 .5.2 1 .5 1.5.3.5.5 1 .5 1.5a3 3 0 0 1-3 3z" />
            <circle cx="13.5" cy="6.5" r="1.5" />
            <circle cx="17.5" cy="10.5" r="1.5" />
            <circle cx="8.5" cy="7.5" r="1.5" />
            <circle cx="6.5" cy="12.5" r="1.5" />
          </svg>
        </span>
        <div className="setting-text">
          <b>风格预设</b>
          <span>管理 AI 出图的视觉风格</span>
        </div>
        <span className="setting-arrow" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </span>
      </div>

      <div className="setting-card">
        <span className="setting-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </span>
        <div className="setting-text">
          <b>清除本地缓存</b>
          <span>清理本地偏好数据，不影响云端作品</span>
        </div>
        <Button shape="round" size="small" onClick={() => void clearCache()}>
          清除缓存
        </Button>
      </div>

      <Modal
        title="编辑资料"
        open={profileOpen}
        width={380}
        okText="保存"
        cancelText="取消"
        confirmLoading={profileSaving}
        onOk={saveProfile}
        onCancel={() => setProfileOpen(false)}
        destroyOnHidden
      >
        <Form form={profileForm} layout="vertical" preserve={false}>
          <Form.Item name="nickname" label="昵称" rules={[{ required: true, message: '请输入昵称' }]}>
            <Input maxLength={64} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="修改密码"
        open={pwdOpen}
        width={380}
        okText="保存"
        cancelText="取消"
        confirmLoading={pwdSaving}
        onOk={savePassword}
        onCancel={() => setPwdOpen(false)}
        destroyOnHidden
      >
        <Form form={pwdForm} layout="vertical" preserve={false}>
          <Form.Item
            name="old_password"
            label="原密码"
            rules={[{ required: true, message: '请输入原密码' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { pattern: PASSWORD_PATTERN, message: '8-20 位，须含大写、小写字母和数字' }
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_rule, value: string) {
                  if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                  return Promise.reject(new Error('两次输入的新密码不一致'))
                }
              })
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}