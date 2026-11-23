/**
 * 剧本分区（对应 Editor.vue 第 1089–1187 行 + 第 346–508 行逻辑）。
 *
 * 迁移要点：这是「声明式表格列 → columns 数组」的典型样本。
 * Vue 的 <el-table-column> 逐个映射为 columns 里的一项，
 * 自定义单元格（序号、时长、操作）从 <template #default> 变成 render 函数。
 */
import { PlusOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { AutoComplete, Button, Empty, Form, Input, InputNumber, Modal, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useRef, useState } from 'react'

import { editorApi, type StoryboardPayload } from '@/api/editor'
import type { ApiError } from '@/api/client'
import { confirmDialog, toast } from '@/lib/feedback'
import { SHOT_TYPES, fmtDuration } from '@/lib/entities'
import type { Episode, Storyboard } from '@/types'

interface ScriptTabProps {
  projectId: string
  episodeId: number | null
  episode: Episode | null
  storyboards: Storyboard[]
  onReload: () => Promise<void> | void
}

interface SbFormValues {
  shot_type: string
  description: string
  dialogue: string
  emotion: string
  duration: number
}

const EMPTY_FORM: SbFormValues = {
  shot_type: '中景',
  description: '',
  dialogue: '',
  emotion: '',
  duration: 3
}

export function ScriptTab({ projectId, episodeId, episode, storyboards, onReload }: ScriptTabProps) {
  const [generating, setGenerating] = useState(false)
  const [extracting, setExtracting] = useState(false)

  /* ---------------- 剧本梗概 ---------------- */
  const [scriptText, setScriptText] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  // 用户正在编辑且未保存时，不被 SSE 触发的 reload 覆盖；
  // 但切换剧集是「换了份文档」，必须重置脏标记并载入新集内容。
  const dirtyRef = useRef(false)
  const lastEpisodeIdRef = useRef<number | null | undefined>(undefined)

  useEffect(() => {
    const ep = episode as (Episode & { logline?: string }) | null
    const epId = ep?.id ?? null
    if (epId !== lastEpisodeIdRef.current) {
      lastEpisodeIdRef.current = epId
      dirtyRef.current = false
      setDirty(false)
    }
    if (dirtyRef.current) return
    setScriptText(ep?.synopsis || ep?.logline || '')
  }, [episode])

  function onScriptInput(value: string) {
    dirtyRef.current = true
    setDirty(true)
    setScriptText(value)
  }

  async function saveScriptText() {
    if (!episodeId) return
    setSaving(true)
    try {
      await editorApi.saveSynopsis(episodeId, scriptText)
      dirtyRef.current = false
      setDirty(false)
      toast.success('剧本梗概已保存')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setSaving(false)
    }
  }

  /* ---------------- 生成 / 提取 ---------------- */
  async function generateScript() {
    if (storyboards.length > 0) {
      const ok = await confirmDialog({
        title: '重新生成剧本',
        content: '重新生成剧本会删除本集现有的全部分镜与已生成的画面，确定继续吗？',
        okText: '仍然重新生成',
        cancelText: '取消',
        danger: true
      })
      if (!ok) return
    }
    setGenerating(true)
    try {
      await editorApi.generateScript(projectId, episodeId)
      toast.success('已提交剧本生成任务')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setGenerating(false)
    }
  }

  async function extractChars() {
    if (!episodeId) {
      toast.warning('请先生成剧本')
      return
    }
    setExtracting(true)
    try {
      const r = await editorApi.extractCharacters(episodeId)
      toast.success(`角色提取完成：新增 ${r?.created ?? 0}，更新 ${r?.updated ?? 0}`)
      await onReload()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setExtracting(false)
    }
  }

  /* ---------------- 分镜增改删 / 排序 ---------------- */
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<SbFormValues>()

  function openAdd() {
    setEditingId(null)
    form.setFieldsValue(EMPTY_FORM)
    setDialogOpen(true)
  }

  function openEdit(sb: Storyboard) {
    setEditingId((sb.id as number) ?? null)
    form.setFieldsValue({
      shot_type: (sb.shot_type as string) || '中景',
      description: (sb.description as string) || '',
      dialogue: (sb.dialogue as string) || '',
      emotion: (sb.emotion as string) || '',
      duration: Number(sb.duration) || 3
    })
    setDialogOpen(true)
  }

  async function saveSb() {
    let values: SbFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    const payload: StoryboardPayload = {
      shot_size: values.shot_type,
      scene: values.description,
      dialogue: values.dialogue,
      emotion: values.emotion,
      duration_sec: Math.max(1, Math.round(Number(values.duration) || 3))
    }
    setSubmitting(true)
    try {
      if (editingId) {
        await editorApi.updateStoryboard(editingId, payload)
        toast.success('分镜已更新')
        await onReload()
      } else {
        // 带当前集 id：否则后端回退默认集，在非第 1 集新增会落错集
        await editorApi.createStoryboard(
          projectId,
          episodeId ? { ...payload, episode_id: episodeId } : payload
        )
        toast.success('分镜已新增')
        await onReload()
      }
      setDialogOpen(false)
    } catch (raw) {
      const err = raw as ApiError
      if (err?.fieldErrors) {
        const keys: (keyof SbFormValues)[] = [
          'shot_type',
          'description',
          'dialogue',
          'emotion',
          'duration'
        ]
        const fields = keys
          .filter((k) => err.fieldErrors?.[k])
          .map((k) => ({ name: k, errors: [err.fieldErrors![k]] }))
        if (fields.length) form.setFields(fields)
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function removeSb(sb: Storyboard) {
    const ok = await confirmDialog({
      title: '删除分镜',
      content: '删除后该分镜的镜头与画面版本将一并删除，确定吗？',
      okText: '删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    try {
      await editorApi.deleteStoryboard(sb.id as number)
      toast.success('分镜已删除')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    }
  }

  async function moveSb(index: number, d: number) {
    const j = index + d
    if (j < 0 || j >= storyboards.length) return
    const ordered = [...storyboards]
    const tmp = ordered[index]
    ordered[index] = ordered[j]
    ordered[j] = tmp
    try {
      await editorApi.reorderStoryboards(
        projectId,
        ordered.map((s) => s.id as number | undefined)
      )
      await onReload()
    } catch {
      /* 拦截器已提示 */
    }
  }

  /* ---------------- 表格列 ---------------- */
  const columns: ColumnsType<Storyboard> = [
    {
      title: '序号',
      width: 64,
      align: 'center',
      render: (_v, _r, i) => i + 1
    },
    { title: '景别', dataIndex: 'shot_type', width: 92 },
    { title: '画面描述', dataIndex: 'description', ellipsis: true, width: 260 },
    { title: '台词', dataIndex: 'dialogue', ellipsis: true, width: 220 },
    { title: '情绪', dataIndex: 'emotion', width: 92 },
    {
      title: '时长',
      width: 80,
      render: (_v, r) => fmtDuration(r.duration as number) || '-'
    },
    {
      title: '操作',
      width: 216,
      fixed: 'right',
      render: (_v, r, i) => (
        <div className="sb-ops">
          <Button type="link" size="small" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Button type="link" size="small" disabled={i === 0} onClick={() => void moveSb(i, -1)}>
            上移
          </Button>
          <Button
            type="link"
            size="small"
            disabled={i === storyboards.length - 1}
            onClick={() => void moveSb(i, 1)}
          >
            下移
          </Button>
          <Button type="link" size="small" danger onClick={() => void removeSb(r)}>
            删除
          </Button>
        </div>
      )
    }
  ]

  return (
    <section className="ed-section">
      <div className="ed-step-header">
        <div className="ed-step-badge">
          <span className="ed-step-sub">共 {storyboards.length} 个分镜</span>
        </div>
        <div className="ed-step-ops">
          <Button
            size="small"
            type="primary"
            loading={generating}
            icon={<ThunderboltOutlined />}
            onClick={() => void generateScript()}
          >
            AI 生成分镜脚本
          </Button>
          <Button
            size="small"
            loading={extracting}
            disabled={!storyboards.length}
            icon={<SyncOutlined />}
            onClick={() => void extractChars()}
          >
            重提角色
          </Button>
          <Button size="small" icon={<PlusOutlined />} onClick={openAdd}>
            新增分镜
          </Button>
        </div>
      </div>

      {/* 剧本梗概：存 episode.synopsis，不影响分镜 */}
      <div className="script-text-card">
        <div className="st-head">
          <span className="st-label">剧本梗概（可编辑，不影响分镜）</span>
          <span className="st-count mono">{scriptText.length} 字</span>
          <Button
            size="small"
            type="primary"
            ghost
            disabled={!dirty || !episodeId}
            loading={saving}
            onClick={() => void saveScriptText()}
          >
            保存
          </Button>
        </div>
        <Input.TextArea
          rows={4}
          value={scriptText}
          placeholder="本集故事梗概 / 剧情走向，AI 生成剧本时参考；改完点保存即可，无需重新生成"
          onChange={(e) => onScriptInput(e.target.value)}
        />
      </div>

      {storyboards.length > 0 ? (
        <div className="table-card">
          <Table<Storyboard>
            dataSource={storyboards}
            columns={columns}
            rowKey={(r, i) => String(r.id ?? `idx-${i}`)}
            pagination={false}
            size="small"
            scroll={{ x: 1000 }}
          />
        </div>
      ) : (
        <div className="g-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="还没有分镜脚本，点击「AI 生成分镜脚本」开始"
          />
        </div>
      )}

      <Modal
        title={editingId ? '编辑分镜' : '新增分镜'}
        open={dialogOpen}
        width={520}
        okText="保存"
        cancelText="取消"
        confirmLoading={submitting}
        onOk={saveSb}
        onCancel={() => setDialogOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={EMPTY_FORM} preserve={false}>
          <Form.Item
            name="shot_type"
            label="景别"
            rules={[{ required: true, message: '请选择景别' }]}
          >
            {/* 原版是 allow-create filterable 的 el-select，用 AutoComplete 等价实现可自由输入 */}
            <AutoComplete
              options={SHOT_TYPES.map((v) => ({ value: v }))}
              placeholder="如：中景"
              filterOption={(input, option) => String(option?.value ?? '').includes(input)}
            />
          </Form.Item>
          <Form.Item
            name="description"
            label="画面描述"
            rules={[{ required: true, message: '请填写画面描述' }]}
          >
            <Input.TextArea rows={3} placeholder="具体到人物动作与环境" />
          </Form.Item>
          <Form.Item name="dialogue" label="台词">
            <Input placeholder="没有台词可留空" />
          </Form.Item>
          <Form.Item name="emotion" label="情绪">
            <Input placeholder="如：紧张、温柔" />
          </Form.Item>
          <Form.Item
            name="duration"
            label="时长（秒）"
            rules={[{ required: true, message: '请填写时长' }]}
          >
            <InputNumber min={1} max={30} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  )
}