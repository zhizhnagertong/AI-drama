/** 风格预设管理（对应 Vue 版 views/Styles.vue）。 */
import { PlusOutlined } from '@ant-design/icons'
import { Button, Empty, Form, Input, InputNumber, Modal, Switch, Tag } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import api, { unwrap } from '@/api/client'
import type { ApiError } from '@/api/client'
import { confirmDialog, toast } from '@/lib/feedback'
import { asList } from '@/lib/format'
import { useStylesStore, type StylePreset } from '@/store/styles'

interface StyleFormValues {
  name: string
  prompt: string
  description: string
  negative_prompt: string
  sort_order: number
}

const EMPTY_FORM: StyleFormValues = {
  name: '',
  prompt: '',
  description: '',
  negative_prompt: '',
  sort_order: 0
}

export function Styles() {
  const navigate = useNavigate()
  const refreshStore = useStylesStore((s) => s.fetch)

  const [list, setList] = useState<StylePreset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [includeInactive, setIncludeInactive] = useState(false)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const data = unwrap<unknown>(
        await api.get('/styles', {
          params: { page: 1, page_size: 100, include_inactive: includeInactive }
        })
      )
      setList(asList<StylePreset>(data, 'items', 'styles', 'list'))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [includeInactive])

  useEffect(() => {
    void load()
  }, [load])

  /* ---------------- 启停（乐观更新 + 失败回滚） ---------------- */
  async function toggleActive(s: StylePreset) {
    const prev = s.is_active
    setList((l) => l.map((x) => (x.id === s.id ? { ...x, is_active: !prev } : x)))
    setTogglingId(s.id ?? null)
    try {
      const updated = unwrap<StylePreset>(await api.patch(`/styles/${s.id}/toggle`))
      if (updated && updated.id != null) {
        setList((l) => l.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)))
      }
      void refreshStore(true)
    } catch {
      // 回滚（错误提示由拦截器统一弹出）
      setList((l) => l.map((x) => (x.id === s.id ? { ...x, is_active: prev } : x)))
    } finally {
      setTogglingId(null)
    }
  }

  /* ---------------- 新建 / 编辑 ---------------- */
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [nameError, setNameError] = useState('')
  const [form] = Form.useForm<StyleFormValues>()

  function openCreate() {
    setEditingId(null)
    setNameError('')
    form.setFieldsValue(EMPTY_FORM)
    setDialogOpen(true)
  }

  function openEdit(s: StylePreset) {
    setEditingId(s.id ?? null)
    setNameError('')
    form.setFieldsValue({
      name: s.name || '',
      prompt: (s.prompt as string) || '',
      description: (s.description as string) || '',
      negative_prompt: (s.negative_prompt as string) || '',
      sort_order: Number(s.sort_order) || 0
    })
    setDialogOpen(true)
  }

  async function save() {
    let values: StyleFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setNameError('')
    setSaving(true)
    const payload = {
      name: values.name.trim(),
      prompt: values.prompt.trim(),
      description: values.description.trim(),
      negative_prompt: values.negative_prompt.trim(),
      sort_order: values.sort_order
    }
    try {
      if (editingId == null) {
        const created = unwrap<StylePreset>(
          await api.post('/styles', { ...payload, is_active: true })
        )
        if (created && created.id != null) setList((l) => [...l, created])
        else void load()
        toast.success('风格已创建')
      } else {
        const updated = unwrap<StylePreset>(await api.put(`/styles/${editingId}`, payload))
        if (updated && updated.id != null) {
          setList((l) => l.map((x) => (x.id === editingId ? { ...x, ...updated } : x)))
        } else {
          void load()
        }
        toast.success('风格已更新')
      }
      setDialogOpen(false)
      void refreshStore(true)
    } catch (raw) {
      // 重名 400：拦截器已弹后端消息，这里额外把名称字段标红
      const err = raw as ApiError
      if (err?.status === 400) {
        setNameError(err.friendlyMessage || '风格名称已存在')
      }
    } finally {
      setSaving(false)
    }
  }

  /* ---------------- 删除 ---------------- */
  async function removeStyle(s: StylePreset) {
    const ok = await confirmDialog({
      title: '删除风格',
      content: `确定删除风格「${s.name}」吗？删除后不可恢复。`,
      okText: '删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    try {
      await api.delete(`/styles/${s.id}`)
      setList((l) => l.filter((x) => x.id !== s.id))
      toast.success('风格已删除')
      void refreshStore(true)
    } catch {
      /* 拦截器已提示 */
    }
  }

  /* ---------------- 名称校验：与后端同规则 ---------------- */
  const nameRule = {
    validator: (_rule: unknown, value: string) => {
      if (!value || !String(value).trim()) return Promise.reject(new Error('请输入风格名称'))
      if (value !== String(value).trim()) return Promise.reject(new Error('名称首尾不能包含空格'))
      const len = String(value).trim().length
      if (len < 1 || len > 64) return Promise.reject(new Error('名称长度为 1-64 个字符'))
      return Promise.resolve()
    }
  }

  return (
    <div className="g-page">
      <div className="styles-header">
        <button
          type="button"
          className="back-btn"
          aria-label="返回我的主页"
          onClick={() => navigate('/mine')}
        >
          <svg
            aria-hidden="true"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <div className="styles-header-text">
          <h1 className="g-page-title">风格预设</h1>
          <p className="g-page-sub">管理 AI 出图的视觉风格，创作时可直接选用启用中的风格</p>
        </div>
        <Button type="primary" shape="round" icon={<PlusOutlined />} onClick={openCreate}>
          <span className="new-label">新建风格</span>
        </Button>
      </div>

      <div className="styles-toolbar">
        <Switch
          checked={includeInactive}
          aria-label="显示已停用的风格"
          onChange={setIncludeInactive}
        />
        <span className="toolbar-label">显示已停用</span>
        {!loading && !error && <span className="toolbar-count num">{list.length} 个风格</span>}
      </div>

      <div className="grid-wrap">
        {error ? (
          <div className="g-empty">
            <h3>风格列表加载失败</h3>
            <p>网络异常或服务暂不可用，请稍后重试</p>
            <Button shape="round" onClick={() => void load()}>
              重试
            </Button>
          </div>
        ) : loading ? (
          <div className="styles-loading">加载中…</div>
        ) : list.length ? (
          <div className="styles-grid">
            {list.map((s) => (
              <article
                key={String(s.id ?? s.name)}
                className={`style-card g-card${s.is_active ? '' : ' style-card--off'}`}
              >
                <div className="card-head">
                  <h3 className="style-name" title={s.name}>
                    {s.name}
                  </h3>
                  <Tag color={s.is_active ? 'success' : 'default'}>
                    {s.is_active ? '启用' : '停用'}
                  </Tag>
                </div>
                {s.description && <p className="style-desc">{s.description}</p>}
                <p className="style-prompt mono" title={s.prompt as string}>
                  {(s.prompt as string) || '（未填写提示词）'}
                </p>
                <div className="card-foot">
                  <Switch
                    checked={!!s.is_active}
                    loading={togglingId === s.id}
                    aria-label="启用/停用该风格"
                    onChange={() => void toggleActive(s)}
                  />
                  <div className="card-ops">
                    <Button type="text" size="small" onClick={() => openEdit(s)}>
                      编辑
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      className="op-danger"
                      onClick={() => void removeStyle(s)}
                    >
                      删除
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="g-empty">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <circle cx="13.5" cy="6.5" r="2.5" />
              <circle cx="17.5" cy="10.5" r="2.5" />
              <circle cx="8.5" cy="7.5" r="2.5" />
              <circle cx="6.5" cy="12.5" r="2.5" />
              <path d="M12 22a10 10 0 1 1 10-10c0 1.5-1 2-2 2h-2a2 2 0 0 0-2 2c0 .5.2 1 .5 1.5.3.5.5 1 .5 1.5a3 3 0 0 1-3 3z" />
            </svg>
            <h3>还没有风格预设</h3>
            <p>创建你的第一个视觉风格，让 AI 出图更有辨识度</p>
            <Button type="primary" shape="round" onClick={openCreate}>
              新建风格
            </Button>
          </div>
        )}
      </div>

      <Modal
        title={editingId == null ? '新建风格' : '编辑风格'}
        open={dialogOpen}
        width={520}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        maskClosable={false}
        onOk={save}
        onCancel={() => setDialogOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={EMPTY_FORM} preserve={false}>
          <Form.Item
            name="name"
            label="名称"
            rules={[nameRule]}
            validateStatus={nameError ? 'error' : undefined}
            help={nameError || undefined}
          >
            <Input
              placeholder="如：赛博朋克"
              maxLength={64}
              showCount
              onChange={() => setNameError('')}
            />
          </Form.Item>
          <Form.Item
            name="prompt"
            label="提示词"
            rules={[
              { required: true, message: '请输入提示词' },
              { max: 2000, message: '提示词不能超过 2000 个字符' }
            ]}
          >
            <Input.TextArea
              rows={4}
              maxLength={2000}
              showCount
              placeholder="cyberpunk, neon lights, futuristic city, high contrast, cinematic lighting…"
            />
          </Form.Item>
          <Form.Item name="description" label="简介（可选）">
            <Input maxLength={256} placeholder="一句话描述这个风格的视觉效果" />
          </Form.Item>
          <Form.Item name="negative_prompt" label="负向提示词（可选）">
            <Input.TextArea
              rows={2}
              maxLength={2000}
              showCount
              placeholder="blurry, low quality, watermark…"
            />
          </Form.Item>
          <Form.Item label="排序">
            <div className="sort-row">
              <Form.Item name="sort_order" noStyle>
                <InputNumber min={0} max={999} style={{ width: 120 }} />
              </Form.Item>
              <span className="sort-hint">数值越小越靠前</span>
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}