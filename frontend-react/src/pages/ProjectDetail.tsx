/** 项目详情：头部信息 + 剧集 / 素材库 两个 Tab（对应 Vue 版 views/ProjectDetail.vue）。 */
import {
  ArrowDownOutlined,
  EditOutlined,
  MoreOutlined,
  PlusOutlined,
  VideoCameraOutlined
} from '@ant-design/icons'
import { Button, Dropdown, Empty, Form, Image, Input, Modal, Radio, Select, Spin, Tabs, Tag } from 'antd'
import type { MenuProps } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { confirmDialog, toast } from '@/lib/feedback'
import { fmtTime, firstChar, gradVar, statusText } from '@/lib/format'
import {
  GENRES,
  RATIOS,
  STYLES,
  assetNameOf,
  assetTypeOf,
  assetUrlOf,
  imgOf,
  normStoryboard,
  versionsOf
} from '@/lib/entities'
import { projectsApi } from '@/api/projects'
import { useStylesStore } from '@/store/styles'
import type { Asset, Episode, Project, Storyboard } from '@/types'

interface EpisodeFormValues {
  title: string
  synopsis: string
}

interface EditFormValues {
  title: string
  genre: string
  style: string
  aspect_ratio: string
}

const STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'script_ready', label: '剧本就绪' },
  { value: 'producing', label: '制作中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' }
]

/** 集卡片智能按钮：按 stats 推导下一步 */
function epCta(ep: Episode): { label: string; action: 'editor' | 'pipeline' } {
  const s = (ep.stats || {}) as { has_final?: boolean; storyboard_count?: number }
  if (s.has_final) return { label: '查看成片', action: 'editor' }
  if ((s.storyboard_count || 0) > 0) return { label: '继续制作', action: 'editor' }
  return { label: '开始制作', action: 'pipeline' }
}

function epProgress(ep: Episode): string {
  const s = (ep.stats || {}) as { storyboard_count?: number; completed_count?: number }
  if (!s.storyboard_count) return ''
  return `${s.completed_count || 0}/${s.storyboard_count} 画面`
}

export function ProjectDetail() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [project, setProject] = useState<Project | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [storyboards, setStoryboards] = useState<Storyboard[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('episodes')
  // 生成封面的轮询最多 4 分钟；卸载后必须停止写状态与弹提示
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const presets = useStylesStore((s) => s.presets)
  const storeLoaded = useStylesStore((s) => s.loaded)
  const storeSource = useStylesStore((s) => s.source)
  const fetchStyles = useStylesStore((s) => s.fetch)

  useEffect(() => {
    void fetchStyles()
  }, [fetchStyles])

  /** 风格下拉：后端可达时严格使用启用预设，仅请求失败回退内置 STYLES */
  const styleNames = useMemo(() => {
    const names = presets.map((p) => p.name)
    if (storeLoaded && storeSource === 'remote') return names
    return names.length ? names : STYLES
  }, [presets, storeLoaded, storeSource])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await projectsApi.detail(id)
      setProject(data.project)
      setEpisodes(data.episodes)
      setStoryboards(
        data.storyboards.map((sb, i) => normStoryboard(sb as Record<string, unknown>, i))
      )
      setAssets(data.assets)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  /* ---------------- 封面与基础信息 ---------------- */
  const cover = imgOf(project || {})
  const initial = firstChar(project?.title)
  const ratioText = (project?.aspect_ratio as string) || (project?.ratio as string) || '9:16'

  /* ---------------- 素材聚合 ---------------- */
  const imageList = useMemo(() => {
    const seen = new Set<string>()
    const out: Array<{ url: string; from: string }> = []
    for (const sb of storyboards) {
      for (const v of versionsOf(sb)) {
        const url = imgOf(v as Record<string, unknown>)
        if (url && !seen.has(url)) {
          seen.add(url)
          out.push({ url, from: `第${((sb.order_index as number) ?? 0) + 1}幕` })
        }
      }
    }
    for (const a of assets) {
      const url = assetUrlOf(a as Record<string, unknown>)
      if (assetTypeOf(a as Record<string, unknown>) === 'image' && url && !seen.has(url)) {
        seen.add(url)
        out.push({ url, from: '素材库' })
      }
    }
    return out
  }, [storyboards, assets])

  const audioList = useMemo(
    () =>
      assets
        .filter((a) => assetTypeOf(a as Record<string, unknown>) === 'audio')
        .map((a) => ({
          name: assetNameOf(a as Record<string, unknown>),
          url: assetUrlOf(a as Record<string, unknown>)
        }))
        .filter((a) => a.url),
    [assets]
  )

  const videoList = useMemo(() => {
    const seen = new Set<string>()
    const out: Array<{ url: string; name: string }> = []
    for (const sb of storyboards) {
      for (const sh of sb.shots || []) {
        const url =
          (sh.video_url as string) || (sh.versions || []).find((v) => v.video_url)?.video_url || ''
        if (url && !seen.has(url)) {
          seen.add(url)
          out.push({ url, name: `第${((sb.order_index as number) ?? 0) + 1}幕 · 镜头视频` })
        }
      }
    }
    for (const a of assets) {
      if (assetTypeOf(a as Record<string, unknown>) !== 'video') continue
      const url = assetUrlOf(a as Record<string, unknown>)
      if (url && !seen.has(url)) {
        seen.add(url)
        out.push({ url, name: assetNameOf(a as Record<string, unknown>) })
      }
    }
    return out
  }, [storyboards, assets])

  const assetTotal = imageList.length + audioList.length + videoList.length

  /* ---------------- 剧集增改删 ---------------- */
  const [epOpen, setEpOpen] = useState(false)
  const [epEditingId, setEpEditingId] = useState<number | null>(null)
  const [epSaving, setEpSaving] = useState(false)
  const [epForm] = Form.useForm<EpisodeFormValues>()

  function openAddEp() {
    setEpEditingId(null)
    epForm.setFieldsValue({ title: '', synopsis: '' })
    setEpOpen(true)
  }

  function openEditEp(ep: Episode) {
    setEpEditingId(ep.id)
    epForm.setFieldsValue({ title: ep.title || '', synopsis: ep.synopsis || '' })
    setEpOpen(true)
  }

  async function saveEp() {
    let values: EpisodeFormValues
    try {
      values = await epForm.validateFields()
    } catch {
      return
    }
    setEpSaving(true)
    try {
      if (epEditingId) {
        await projectsApi.updateEpisode(epEditingId, {
          title: values.title,
          synopsis: values.synopsis
        })
      } else {
        await projectsApi.createEpisode(id, {
          title: values.title || undefined,
          synopsis: values.synopsis || undefined
        })
      }
      setEpOpen(false)
      await load()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setEpSaving(false)
    }
  }

  async function removeEp(ep: Episode) {
    const ok = await confirmDialog({
      title: '删除剧集',
      content: `确定删除「${ep.title}」吗？该集的分镜与生成记录将保留但不再可达。`,
      okText: '删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    try {
      await projectsApi.removeEpisode(ep.id)
      toast.success('剧集已删除')
      await load()
    } catch {
      /* 拦截器已提示 */
    }
  }

  async function genEpScript(ep: Episode) {
    try {
      await projectsApi.generateEpisodeScript(ep.id)
      toast.success(`已提交「${ep.title}」剧本生成任务`)
    } catch {
      /* 拦截器已提示 */
    }
  }

  async function runEpPipeline(ep: Episode) {
    try {
      await projectsApi.runEpisodePipeline(ep.id)
      toast.success(`「${ep.title}」一键流水线已启动`)
    } catch {
      /* 拦截器已提示 */
    }
  }

  function openEpEditor(ep: Episode) {
    navigate(`/editor/${id}?episode=${ep.id}`)
  }

  async function handleEpCmd(cmd: string, ep: Episode) {
    if (cmd === 'edit') openEditEp(ep)
    else if (cmd === 'delete') await removeEp(ep)
    else if (cmd === 'editor') openEpEditor(ep)
    else if (cmd === 'script') await genEpScript(ep)
    else if (cmd === 'pipeline') await runEpPipeline(ep)
  }

  /* ---------------- 项目状态手动标记（乐观更新） ---------------- */
  async function setProjectStatus(val: string) {
    if (!project || project.status === val) return
    const prev = project.status
    setProject({ ...project, status: val })
    try {
      await projectsApi.update(id, { status: val })
    } catch {
      setProject((p) => (p ? { ...p, status: prev } : p))
    }
  }

  /* ---------------- 编辑项目 ---------------- */
  const [editOpen, setEditOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [coverGenerating, setCoverGenerating] = useState(false)
  const [editForm] = Form.useForm<EditFormValues>()

  function openEdit() {
    editForm.setFieldsValue({
      title: project?.title || '',
      genre: (project?.genre as string) || '其他',
      style: (project?.style as string) || STYLES[0],
      aspect_ratio: ratioText
    })
    setEditOpen(true)
  }

  async function saveEdit() {
    let values: EditFormValues
    try {
      values = await editForm.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      await projectsApi.update(id, values)
      setProject((p) => (p ? { ...p, ...values } : p))
      setEditOpen(false)
      toast.success('项目已更新')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setSaving(false)
    }
  }

  /** 生成封面：提交任务后轮询 /tasks/{id}（最多 120 次 × 2s） */
  async function generateCover() {
    if (coverGenerating) return
    setCoverGenerating(true)
    try {
      const { task_id } = await projectsApi.generateCover(id)
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => window.setTimeout(r, 2000))
        if (!mountedRef.current) return
        const t = await projectsApi.getTask(task_id)
        if (!mountedRef.current) return
        if (t?.status === 'succeeded') {
          toast.success('封面已生成')
          await load()
          return
        }
        if (t?.status === 'failed') {
          toast.error(`封面生成失败：${t.error || '未知错误'}`)
          return
        }
      }
      if (mountedRef.current) toast.warning('封面生成超时，请稍后刷新查看')
    } catch {
      /* 拦截器已提示 */
    } finally {
      if (mountedRef.current) setCoverGenerating(false)
    }
  }

  async function setAsCover(url: string) {
    if (!url) return
    try {
      await projectsApi.update(id, { cover_url: url })
      setProject((p) => (p ? { ...p, cover_url: url } : p))
      toast.success('已设为项目封面')
    } catch {
      /* 拦截器已提示 */
    }
  }

  /* ---------------- 删除项目（两重确认） ---------------- */
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteInput, setDeleteInput] = useState('')
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)

  async function startDelete() {
    const title = project?.title || '未命名项目'
    const ok = await confirmDialog({
      title: '删除项目',
      content: `确定删除项目「${title}」吗？该项目的所有剧集、分镜、生成图片与视频将被一并删除。`,
      okText: '继续删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    setDeleteInput('')
    setDeleteError('')
    setDeleteOpen(true)
  }

  async function doDelete() {
    const title = project?.title || '未命名项目'
    if (deleteInput.trim() !== title) {
      setDeleteError('项目名不匹配')
      return
    }
    setDeleting(true)
    try {
      await projectsApi.remove(Number(id))
      toast.success('项目已彻底删除')
      setDeleteOpen(false)
      navigate('/')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setDeleting(false)
    }
  }

  /* ---------------- 渲染 ---------------- */
  if (loading && !project) {
    return (
      <div className="pd-loading">
        <Spin size="large" />
      </div>
    )
  }

  const epMenu = (ep: Episode): MenuProps['items'] => [
    { key: 'editor', label: '进入工作台' },
    { key: 'script', label: '生成剧本' },
    { key: 'pipeline', label: '一键流水线' },
    { type: 'divider' },
    { key: 'edit', label: '编辑' },
    { key: 'delete', label: '删除', danger: true }
  ]

  const episodesPane = (
    <>
      <div className="tab-toolbar">
        <Button
          type="primary"
          shape="round"
          size="small"
          icon={<PlusOutlined />}
          onClick={openAddEp}
        >
          新增剧集
        </Button>
      </div>

      {episodes.length ? (
        <div className="episode-grid">
          {episodes.map((ep) => {
            const cta = epCta(ep)
            const progress = epProgress(ep)
            const stats = (ep.stats || {}) as {
              storyboard_count?: number
              video_count?: number
              has_final?: boolean
            }
            return (
              <div key={ep.id} className="episode-card g-card">
                <div className="episode-card-head">
                  <div className="ep-num">
                    <span className="label">EP</span>
                    <b>{String(ep.episode_number ?? 1).padStart(2, '0')}</b>
                  </div>
                  <Tag>{statusText(ep.status)}</Tag>
                </div>
                <div className="episode-card-title" title={ep.title}>
                  {ep.title || `第${ep.episode_number ?? 1}集`}
                </div>
                <div className="episode-card-syn" title={ep.synopsis}>
                  {ep.synopsis || '（暂无梗概）'}
                </div>
                <div className="episode-card-stats">
                  <span>{stats.storyboard_count ?? 0} 分镜</span>
                  <span>{stats.video_count ?? 0} 视频</span>
                  {progress && <span className="mono">{progress}</span>}
                  {stats.has_final && <span className="ok">已有成片</span>}
                </div>
                <div className="episode-card-ops">
                  <Button
                    type="primary"
                    size="small"
                    shape="round"
                    onClick={() =>
                      cta.action === 'editor' ? openEpEditor(ep) : void runEpPipeline(ep)
                    }
                  >
                    {cta.label}
                  </Button>
                  <Dropdown
                    menu={{ items: epMenu(ep), onClick: ({ key }) => void handleEpCmd(key, ep) }}
                    trigger={['click']}
                  >
                    <Button size="small" shape="round" icon={<MoreOutlined />} aria-label="更多操作" />
                  </Dropdown>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="g-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有剧集，点击「新增剧集」开始">
            <Button type="primary" shape="round" onClick={openAddEp}>
              新增剧集
            </Button>
          </Empty>
        </div>
      )}
    </>
  )

  const assetsPane = assetTotal ? (
    <>
      {imageList.length > 0 && (
        <>
          <h3 className="asset-title">图片（{imageList.length}）</h3>
          <Image.PreviewGroup items={imageList.map((x) => x.url)}>
            <div className="asset-grid">
              {imageList.map((img, i) => (
                <div key={img.url} className="asset-card g-card">
                  <div className="asset-thumb">
                    <Image src={img.url} alt={`素材图片 ${i + 1}（${img.from}）`} height={132} />
                    <span className="kind">{img.from}</span>
                    <Button
                      className="set-cover-btn"
                      type="primary"
                      size="small"
                      shape="round"
                      disabled={cover === img.url}
                      onClick={(e) => {
                        e.stopPropagation()
                        void setAsCover(img.url)
                      }}
                    >
                      {cover === img.url ? '已是封面' : '设为封面'}
                    </Button>
                  </div>
                  <div className="asset-name">图片 {i + 1}</div>
                </div>
              ))}
            </div>
          </Image.PreviewGroup>
        </>
      )}

      {videoList.length > 0 && (
        <>
          <h3 className="asset-title">视频（{videoList.length}）</h3>
          <div className="av-grid">
            {videoList.map((v) => (
              <div key={v.url} className="av-cell g-card">
                <video src={v.url} controls preload="metadata" />
                <span className="av-name">{v.name}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {audioList.length > 0 && (
        <>
          <h3 className="asset-title">音频（{audioList.length}）</h3>
          <div className="audio-list">
            {audioList.map((a) => (
              <div key={a.url} className="audio-row g-card">
                <span className="a-name">{a.name}</span>
                <audio src={a.url} controls preload="none" />
              </div>
            ))}
          </div>
        </>
      )}
    </>
  ) : (
    <div className="g-empty">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无素材，生成的画面 / 音频 / 视频会汇集到这里"
      />
    </div>
  )

  return (
    <div className="g-page">
      <div className="project-detail-header">
        <button
          type="button"
          className="back-btn"
          aria-label="返回工作台"
          onClick={() => navigate('/')}
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
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <div className="cover">
          {cover ? (
            <img src={cover} alt={`${project?.title || '未命名项目'} 封面`} width={640} height={360} />
          ) : (
            <div className="cover-grad" style={{ background: gradVar(Number(id) || 0) }}>
              <span>{initial}</span>
            </div>
          )}
        </div>

        <div className="project-detail-info">
          <div className="title-line">
            <h1 className="title">{project?.title || '未命名项目'}</h1>
            <Dropdown
              menu={{
                items: STATUS_OPTIONS.map((s) => ({
                  key: s.value,
                  label: s.label,
                  disabled: project?.status === s.value
                })),
                onClick: ({ key }) => void setProjectStatus(key)
              }}
              trigger={['click']}
            >
              <Tag className="status-badge" title="点击标记项目状态">
                {statusText(project?.status)}
                <ArrowDownOutlined className="status-caret" />
              </Tag>
            </Dropdown>
          </div>

          <div className="project-detail-meta">
            <span className="tag tag-primary">{(project?.genre as string) || '其他'}</span>
            <span className="tag tag-primary">{(project?.style as string) || '未指定风格'}</span>
            <span className="tag">{ratioText}</span>
            <span>{episodes.length} 集</span>
            <span>{storyboards.length} 分镜</span>
            <span>{assetTotal} 素材</span>
            <span>
              创建于 {fmtTime(project?.created_at as string)}
              {project?.updated_at ? ` · 更新于 ${fmtTime(project.updated_at as string)}` : ''}
            </span>
          </div>

          {(project?.inspiration as string) && (
            <div className="insp">灵感：{project?.inspiration as string}</div>
          )}
        </div>

        <div className="ops">
          <Button shape="round" icon={<EditOutlined />} onClick={openEdit}>
            编辑
          </Button>
          <Button
            shape="round"
            type="primary"
            icon={<VideoCameraOutlined />}
            onClick={() => navigate(`/editor/${id}`)}
          >
            进入创作工作台
          </Button>
          <Button shape="round" danger onClick={() => void startDelete()}>
            删除项目
          </Button>
        </div>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        className="detail-tabs"
        items={[
          {
            key: 'episodes',
            label: (
              <span className="tab-label">
                剧集<span className="count">{episodes.length}</span>
              </span>
            ),
            children: episodesPane
          },
          {
            key: 'assets',
            label: (
              <span className="tab-label">
                素材库<span className="count">{assetTotal}</span>
              </span>
            ),
            children: assetsPane
          }
        ]}
      />

      {/* 编辑项目 */}
      <Modal
        title="编辑项目"
        open={editOpen}
        width={440}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        onOk={saveEdit}
        onCancel={() => setEditOpen(false)}
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={40} />
          </Form.Item>
          <Form.Item name="genre" label="题材">
            <Select options={GENRES.map((g) => ({ value: g, label: g }))} />
          </Form.Item>
          <Form.Item name="style" label="风格">
            <Select options={styleNames.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="aspect_ratio" label="画面比例">
            <Radio.Group>
              {RATIOS.map((r) => (
                <Radio.Button key={r.value} value={r.value}>
                  {r.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Form.Item>
          <Form.Item label="封面">
            <div className="cover-row">
              <div className="cover-preview">
                {cover ? (
                  <img src={cover} alt="项目封面" />
                ) : (
                  <div className="cover-grad" style={{ background: gradVar(Number(id) || 0) }}>
                    <span>{initial}</span>
                  </div>
                )}
              </div>
              <div className="cover-actions">
                <Button
                  size="small"
                  shape="round"
                  loading={coverGenerating}
                  onClick={() => void generateCover()}
                >
                  {cover ? '重新生成封面' : '生成封面'}
                </Button>
                <span className="cover-hint">也可到「素材库」中选定画面设为封面</span>
              </div>
            </div>
          </Form.Item>
        </Form>
      </Modal>

      {/* 新增 / 编辑剧集 */}
      <Modal
        title={epEditingId ? '编辑剧集' : '新增剧集'}
        open={epOpen}
        width={440}
        okText="保存"
        cancelText="取消"
        confirmLoading={epSaving}
        onOk={saveEp}
        onCancel={() => setEpOpen(false)}
        destroyOnHidden
      >
        <Form form={epForm} layout="vertical" preserve={false}>
          <Form.Item name="title" label="剧集标题">
            <Input placeholder="留空则自动命名为「第 N 集」" maxLength={40} />
          </Form.Item>
          <Form.Item name="synopsis" label="本集梗概">
            <Input.TextArea rows={3} placeholder="这一集讲什么（供 AI 编剧参考）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 二次确认删除 */}
      <Modal
        title="再次确认"
        open={deleteOpen}
        centered
        okText="彻底删除"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: deleting }}
        onOk={doDelete}
        onCancel={() => setDeleteOpen(false)}
        destroyOnHidden
      >
        <p className="delete-warn">
          此操作不可恢复！请输入项目名「<strong>{project?.title || '未命名项目'}</strong>
          」以确认彻底删除。
        </p>
        <Input
          value={deleteInput}
          placeholder={project?.title || '未命名项目'}
          status={deleteError ? 'error' : undefined}
          onChange={(e) => {
            setDeleteInput(e.target.value)
            if (deleteError) setDeleteError('')
          }}
          onPressEnter={doDelete}
        />
        {deleteError && <p className="delete-error">{deleteError}</p>}
      </Modal>
    </div>
  )
}