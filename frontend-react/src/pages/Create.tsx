/** 创作页：灵感（可拖入文件）→ 一键 AI 流水线。对应 Vue 版 views/Create.vue。 */
import { Button, Input, Select } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import api, { unwrap } from '@/api/client'
import { toast } from '@/lib/feedback'
import { GENRES, RATIOS, STYLES } from '@/lib/entities'
import { MAX_IMPORT_CHARS, MAX_TOTAL_CHARS, extractText } from '@/lib/importText'
import { useStylesStore } from '@/store/styles'

interface ImportedFile {
  name: string
  text: string
  expanded: boolean
}

interface CreateForm {
  title: string
  genre: string
  style: string
  aspect_ratio: string
  inspiration: string
}

/** 风格描述：优先用后端预设 description，本地字典作 fallback */
const STYLE_DESC: Record<string, string> = {
  赛博朋克: '霓虹光效、未来都市',
  水墨国风: '水墨笔触、东方意境',
  日系动漫: '清新线条、高饱和',
  美式漫画: '强对比块面、硬派',
  '3D卡通': '圆润立体、玩具质感',
  写实: '电影感光影、细节'
}

export function Create() {
  const navigate = useNavigate()
  const presets = useStylesStore((s) => s.presets)
  const loaded = useStylesStore((s) => s.loaded)
  const source = useStylesStore((s) => s.source)
  const fetchStyles = useStylesStore((s) => s.fetch)

  const [form, setForm] = useState<CreateForm>({
    title: '',
    genre: '科幻',
    style: '赛博朋克',
    aspect_ratio: '9:16',
    inspiration: ''
  })
  const [importedFiles, setImportedFiles] = useState<ImportedFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [importing, setImporting] = useState(false)
  const [creating, setCreating] = useState(false)

  /* 风格选项：后端可达时严格用预设（全部停用则为空），仅请求失败回退内置常量 */
  const styleOptions = useMemo(() => {
    const list =
      loaded && source === 'remote'
        ? presets
        : presets.length
          ? presets
          : STYLES.map((name) => ({ name, description: '' }))
    return list.map((p) => ({
      name: p.name,
      desc: (p.description as string) || STYLE_DESC[p.name] || 'AI 视觉风格'
    }))
  }, [presets, loaded, source])

  useEffect(() => {
    // 强制刷新，确保与「风格预设」管理页的启停/增删即时同步
    void fetchStyles(true)
  }, [fetchStyles])

  // 当前选中风格不在可选列表时，回落到第一个
  useEffect(() => {
    if (!styleOptions.some((s) => s.name === form.style) && styleOptions[0]) {
      setForm((f) => ({ ...f, style: styleOptions[0].name }))
    }
  }, [styleOptions, form.style])

  const canSubmit = form.inspiration.trim().length > 0 || importedFiles.length > 0

  function patch(part: Partial<CreateForm>) {
    setForm((f) => ({ ...f, ...part }))
  }

  /* ---------------- 文件导入 ---------------- */
  const onDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer?.files || [])
    if (!files.length) return
    setImporting(true)
    let ok = 0
    try {
      for (const f of files) {
        try {
          const text = await extractText(f)
          if (text == null) {
            toast.warning(`暂不支持 ${f.name}，请使用 .txt / .md / .docx 文件`)
            continue
          }
          const t = text.trim()
          if (!t) {
            toast.warning(`${f.name} 内容为空`)
            continue
          }
          let clipped = t
          if (clipped.length > MAX_IMPORT_CHARS) {
            clipped = clipped.slice(0, MAX_IMPORT_CHARS)
            toast.warning(`${f.name} 内容过长，已截取前 ${MAX_IMPORT_CHARS} 字`)
          }
          setImportedFiles((prev) => [...prev, { name: f.name, text: clipped, expanded: false }])
          ok++
        } catch {
          toast.error(`${f.name} 解析失败，请另存为 .txt 后重试`)
        }
      }
      if (ok) toast.success(`已导入 ${ok} 个文件`)
    } finally {
      setImporting(false)
    }
  }, [])

  function removeFile(idx: number) {
    setImportedFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  function toggleExpand(idx: number) {
    setImportedFiles((prev) =>
      prev.map((f, i) => (i === idx ? { ...f, expanded: !f.expanded } : f))
    )
  }

  /** 提交时把文字描述与文件内容组合为灵感文本（带来源标记，供 AI 区分） */
  function buildInspiration(): string {
    const parts: string[] = []
    const desc = form.inspiration.trim()
    if (desc) parts.push(desc)
    for (const f of importedFiles) parts.push(`【文件：${f.name}】\n${f.text}`)
    let merged = parts.join('\n\n')
    if (merged.length > MAX_TOTAL_CHARS) merged = merged.slice(0, MAX_TOTAL_CHARS)
    return merged
  }

  async function createPipeline() {
    if (!canSubmit) {
      toast.warning('输入故事灵感，或拖入文本文件')
      return
    }
    setCreating(true)
    try {
      const project = unwrap<{ id?: number; project?: { id?: number } }>(
        await api.post('/projects', { ...form, inspiration: buildInspiration() })
      )
      const id = project?.id ?? project?.project?.id
      if (!id) throw new Error('创建项目失败')
      await api.post(`/projects/${id}/pipeline`)
      toast.success('AI 流水线已启动，正在为你生成剧本…')
      navigate(`/editor/${id}`)
    } catch {
      /* 错误提示由拦截器统一处理 */
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="g-page">
      <div className="create-layout">
        <div className="create-panel">
          <h2>开始创作</h2>
          <p>输入一个灵感，AI 自动生成剧本、分镜、角色与成片</p>

          <div className="field-group">
            <label className="field-label" htmlFor="inspiration-input">
              创作灵感 <span className="required">*</span>
            </label>
            <div
              className={`inspiration-drop${dragOver ? ' drag-over' : ''}${importing ? ' importing' : ''}`}
              onDragEnter={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={(e) => {
                e.preventDefault()
                if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false)
              }}
              onDrop={onDrop}
            >
              <textarea
                id="inspiration-input"
                className="inspiration"
                rows={5}
                aria-label="创作灵感"
                value={form.inspiration}
                onChange={(e) => patch({ inspiration: e.target.value })}
                placeholder={
                  '输入你的故事灵感…\n支持一句话点子、故事梗概或小说片段，例如：\n「赛博朋克都市里，一个失忆的外卖骑手发现自己救过的人都是同一个女孩…」'
                }
              />
              {dragOver && (
                <div className="drop-mask">
                  <span>松开导入文件</span>
                </div>
              )}
            </div>

            {importedFiles.length > 0 && (
              <div className="file-list">
                {importedFiles.map((f, i) => (
                  <div key={`${f.name}-${i}`} className="file-item">
                    <button type="button" className="file-name" title={f.text} onClick={() => toggleExpand(i)}>
                      <svg
                        aria-hidden="true"
                        width="13"
                        height="13"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <path d="M14 2v6h6" />
                      </svg>
                      <span className="file-name-text">{f.name}</span>
                      <span className="file-meta">
                        {f.text.length} 字 {f.expanded ? '▲' : '▼'}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="file-remove"
                      aria-label="移除文件"
                      onClick={() => removeFile(i)}
                    >
                      ×
                    </button>
                    {f.expanded && <pre className="file-preview">{f.text}</pre>}
                  </div>
                ))}
              </div>
            )}

            <span className="drop-hint">
              {importing ? '正在解析文件…' : '可拖入 .txt / .md / .docx 文件'}
            </span>
          </div>

          <div className="field-group">
            <label className="field-label">标题（可选）</label>
            <Input
              className="field-input"
              placeholder="留给 AI 起名也可以"
              maxLength={30}
              value={form.title}
              onChange={(e) => patch({ title: e.target.value })}
            />
          </div>

          <div className="field-group">
            <label className="field-label">题材</label>
            <Select
              className="field-input"
              value={form.genre}
              onChange={(v: string) => patch({ genre: v })}
              options={GENRES.map((g) => ({ value: g, label: g }))}
              style={{ width: '100%' }}
            />
          </div>

          <div className="field-group">
            <label className="field-label">视觉风格</label>
            {styleOptions.length ? (
              <div className="style-grid">
                {styleOptions.map((s) => (
                  <button
                    key={s.name}
                    type="button"
                    className={`style-option${form.style === s.name ? ' on' : ''}`}
                    onClick={() => patch({ style: s.name })}
                  >
                    <b>{s.name}</b>
                    <span>{s.desc}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="style-empty">
                暂无启用中的视觉风格，请先到 <Link to="/styles">风格预设</Link> 启用或新建风格
              </div>
            )}
          </div>

          <div className="field-group">
            <label className="field-label">画面比例</label>
            <div className="aspect-row">
              {RATIOS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  className={`aspect-option${form.aspect_ratio === r.value ? ' on' : ''}`}
                  onClick={() => patch({ aspect_ratio: r.value })}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          <div className="create-btn-area">
            <Button
              className="generate-btn"
              type="primary"
              size="large"
              loading={creating}
              disabled={!canSubmit}
              onClick={() => void createPipeline()}
            >
              <svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path d="M12 2l2.4 7.2L22 11l-7.6 2.8L12 22l-2.4-8.2L2 11l7.6-1.8z" />
              </svg>
              <span className="generate-label">{creating ? '生成中…' : '一键 AI 生成'}</span>
            </Button>
            <span className="hint">将依次生成：剧本 → 角色 → 分镜 → 画面 → 配音 → 成片</span>
          </div>
        </div>
      </div>
    </div>
  )
}