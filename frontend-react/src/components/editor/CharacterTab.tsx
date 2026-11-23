/**
 * 角色分区（对应 Editor.vue 第 1188–1249 行 + 第 510–613 行逻辑）。
 *
 * 关键迁移点：试听用的 `new Audio(url)` 是命令式副作用，
 * 在 React 里必须自己持有实例并在卸载时 pause，否则切走 Tab 后音频还在放。
 */
import { AudioOutlined, EditOutlined, PictureOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Empty, Form, Input, Modal, Select, Tag } from 'antd'
import { useEffect, useRef, useState } from 'react'

import { editorApi, type CharacterPayload } from '@/api/editor'
import type { ApiError } from '@/api/client'
import { confirmDialog, toast } from '@/lib/feedback'
import { VOICES, firstCharOf, gradVarOf, imgOf, voiceLabel } from '@/lib/entities'
import type { Character } from '@/types'

interface CharacterTabProps {
  projectId: string
  characters: Character[]
  onReload: () => Promise<void> | void
}

interface CharFormValues {
  name: string
  description: string
  prompt_template: string
  voice: string
}

const EMPTY_FORM: CharFormValues = {
  name: '',
  description: '',
  prompt_template: '',
  voice: 'longxiaochun'
}

export function CharacterTab({ projectId, characters, onReload }: CharacterTabProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<CharFormValues>()

  // 生成参考图：按角色 id 记 loading（原版是 reactive({}) 字典）
  const [refLoading, setRefLoading] = useState<Record<number, boolean>>({})

  // 单例音频：切换角色时先停上一条
  const audioRef = useRef<HTMLAudioElement | null>(null)
  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      audioRef.current = null
    }
  }, [])

  function playAudio(url: string) {
    if (!url) {
      toast.warning('暂无试听音频')
      return
    }
    audioRef.current?.pause()
    const audio = new Audio(url)
    audioRef.current = audio
    audio.play().catch(() => toast.warning('音频播放失败'))
  }

  function openAdd() {
    setEditingId(null)
    form.setFieldsValue(EMPTY_FORM)
    setDialogOpen(true)
  }

  function openEdit(c: Character) {
    setEditingId((c.id as number) ?? null)
    form.setFieldsValue({
      name: (c.name as string) || '',
      description: (c.description as string) || '',
      prompt_template: ((c.prompt_template || c.prompt) as string) || '',
      voice: (c.voice as string) || 'longxiaochun'
    })
    setDialogOpen(true)
  }

  async function saveChar() {
    let values: CharFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    const payload: CharacterPayload = {
      name: values.name,
      description: values.description,
      prompt_template: values.prompt_template,
      voice: values.voice
    }
    setSubmitting(true)
    try {
      if (editingId) {
        await editorApi.updateCharacter(editingId, payload)
        toast.success('角色已更新')
      } else {
        await editorApi.createCharacter(projectId, payload)
        toast.success('角色已新增')
      }
      setDialogOpen(false)
      await onReload()
    } catch (raw) {
      const err = raw as ApiError
      if (err?.fieldErrors) {
        const keys: (keyof CharFormValues)[] = ['name', 'description', 'prompt_template', 'voice']
        const fields = keys
          .filter((k) => err.fieldErrors?.[k])
          .map((k) => ({ name: k, errors: [err.fieldErrors![k]] }))
        if (fields.length) form.setFields(fields)
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function removeChar(c: Character) {
    const ok = await confirmDialog({
      title: '删除角色',
      content: `确定删除角色「${c.name || '未命名角色'}」吗？`,
      okText: '删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    try {
      await editorApi.deleteCharacter(c.id as number)
      toast.success('角色已删除')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    }
  }

  async function genRef(c: Character) {
    const id = c.id as number
    setRefLoading((prev) => ({ ...prev, [id]: true }))
    try {
      await editorApi.generateRef(id)
      toast.success('已提交参考图生成任务')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setRefLoading((prev) => ({ ...prev, [id]: false }))
    }
  }

  async function audition(c: Character) {
    try {
      const data = await editorApi.audition(c.id as number)
      const url =
        typeof data === 'string'
          ? data
          : ((data as { audio_url?: string; url?: string })?.audio_url ||
            (data as { url?: string })?.url ||
            '')
      playAudio(url || '')
    } catch {
      /* 拦截器已提示 */
    }
  }

  return (
    <section className="ed-section">
      <div className="ed-step-header">
        <div className="ed-step-badge">
          <span className="ed-step-sub">{characters.length} 个角色</span>
        </div>
        <div className="ed-step-ops">
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={openAdd}>
            新增角色
          </Button>
        </div>
      </div>

      {characters.length ? (
        <div className="char-grid">
          {characters.map((c) => {
            const cover = imgOf(c as Record<string, unknown>)
            const id = c.id as number
            return (
              <div key={String(id ?? c.name)} className="char-card">
                <div
                  className="char-visual"
                  style={cover ? undefined : { background: gradVarOf(id) }}
                >
                  {cover ? (
                    <img
                      src={cover}
                      alt={`${c.name || '未命名角色'} 参考图`}
                      loading="lazy"
                      width={640}
                      height={640}
                    />
                  ) : (
                    <span className="letter">{firstCharOf(c.name)}</span>
                  )}
                </div>
                <div className="char-info">
                  <h4>{c.name || '未命名角色'}</h4>
                  <p>{c.description || '暂无描述'}</p>
                  <div className="char-tags">
                    <Tag>{voiceLabel(c.voice)}</Tag>
                  </div>
                  <div className="char-actions">
                    <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(c)}>
                      编辑
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      icon={<PictureOutlined />}
                      loading={!!refLoading[id]}
                      onClick={() => void genRef(c)}
                    >
                      生成参考图
                    </Button>
                    <Button
                      size="small"
                      type="link"
                      icon={<AudioOutlined />}
                      onClick={() => void audition(c)}
                    >
                      试听
                    </Button>
                    <Button size="small" type="link" danger onClick={() => void removeChar(c)}>
                      删除
                    </Button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="g-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="剧本生成后将自动提取角色设定" />
        </div>
      )}

      <Modal
        title={editingId ? '编辑角色' : '新增角色'}
        open={dialogOpen}
        width={520}
        okText="保存"
        cancelText="取消"
        confirmLoading={submitting}
        onOk={saveChar}
        onCancel={() => setDialogOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={EMPTY_FORM} preserve={false}>
          <div className="form-grid">
            <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}>
              <Input maxLength={20} placeholder="角色名" />
            </Form.Item>
            <Form.Item name="voice" label="音色">
              <Select options={VOICES} />
            </Form.Item>
          </div>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="性格与背景简介" />
          </Form.Item>
          <Form.Item name="prompt_template" label="提示词模板">
            <Input.TextArea
              rows={3}
              placeholder="用于生成角色参考图的提示词模板（只写外貌，不写画风）"
            />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  )
}