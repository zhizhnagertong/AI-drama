/**
 * 画面分镜分区（对应 Editor.vue 第 1250–1389 行 + 第 615–801 行逻辑）。
 *
 * ⚠️ React 迁移的三个高风险点在 this file 里都有体现：
 * 1) batchSel 是 Set —— 必须 `new Set(prev)` 换引用，就地 add/delete 不会触发渲染；
 * 2) 批量提交成功后要同时清空「批量模式 + 选择集」，两处状态不能只改一个；
 * 3) 版本「选定」是服务端动作 + reload，不能只改本地 is_selected。
 */
import { PictureOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { Button, Empty, Image, Input, InputNumber, Modal, Select, Tag } from 'antd'
import { useMemo, useState } from 'react'

import { editorApi } from '@/api/editor'
import { confirmDialog, toast } from '@/lib/feedback'
import {
  fmtDuration,
  gradVarOf,
  hasSelected,
  imgOf,
  selectedOf,
  selectedShots,
  thumbOf,
  versionsOf,
  videoUrlOf
} from '@/lib/entities'
import type { ShotVersion, Storyboard } from '@/types'

interface BoardTabProps {
  episodeId: number | null
  storyboards: Storyboard[]
  onReload: () => Promise<void> | void
}

interface VersionEditState {
  shotId: number
  versionId: number
  prompt: string
  seed: number | null
}

export function BoardTab({ episodeId, storyboards, onReload }: BoardTabProps) {
  /* ---------------- 批量模式 ---------------- */
  const [batchMode, setBatchMode] = useState(false)
  const [batchSel, setBatchSel] = useState<Set<number>>(new Set())

  function toggleBatchMode() {
    setBatchMode((v) => {
      if (v) setBatchSel(new Set())
      return !v
    })
  }

  function toggleBatchSel(id: number) {
    // 必须构造新 Set，否则引用不变、React 认为状态没变
    setBatchSel((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectAll() {
    setBatchSel(new Set(storyboards.map((sb) => sb.id as number).filter(Boolean)))
  }

  const [batchImageOpen, setBatchImageOpen] = useState(false)
  const [batchImageCount, setBatchImageCount] = useState(2)
  const [batchVideoOpen, setBatchVideoOpen] = useState(false)
  const [batchVideoSeconds, setBatchVideoSeconds] = useState('5')
  const [batchSubmitting, setBatchSubmitting] = useState(false)

  async function confirmBatchImages() {
    if (!episodeId) {
      toast.warning('请先选择剧集')
      return
    }
    setBatchSubmitting(true)
    try {
      const r = await editorApi.batchImages(episodeId, {
        storyboard_ids: [...batchSel],
        count: batchImageCount
      })
      setBatchImageOpen(false)
      setBatchMode(false)
      setBatchSel(new Set())
      toast.success(`已提交 ${r?.submitted ?? 0} 个画面生成任务`)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setBatchSubmitting(false)
    }
  }

  async function confirmBatchVideos() {
    if (!episodeId) {
      toast.warning('请先选择剧集')
      return
    }
    setBatchSubmitting(true)
    try {
      const r = await editorApi.batchVideos(episodeId, {
        storyboard_ids: [...batchSel],
        seconds: batchVideoSeconds
      })
      setBatchVideoOpen(false)
      setBatchMode(false)
      setBatchSel(new Set())
      const skipped = (r?.skipped || []).length
      toast.success(
        `已提交 ${r?.submitted ?? 0} 个视频生成任务${
          skipped ? `，跳过 ${skipped} 个（无选定画面或已有视频）` : ''
        }`
      )
    } catch {
      /* 拦截器已提示 */
    } finally {
      setBatchSubmitting(false)
    }
  }

  /* ---------------- 单镜生成画面 ---------------- */
  const [genOpen, setGenOpen] = useState(false)
  const [genSbId, setGenSbId] = useState<number | null>(null)
  const [genCount, setGenCount] = useState(2)
  const [generating, setGenerating] = useState(false)

  function openGenImage(sb: Storyboard) {
    setGenSbId(sb.id as number)
    setGenCount(2)
    setGenOpen(true)
  }

  async function confirmGen() {
    if (!genSbId) return
    setGenerating(true)
    try {
      await editorApi.generateImage(genSbId, genCount)
      setGenOpen(false)
      toast.success(`已提交 ${genCount} 张画面生成任务`)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setGenerating(false)
    }
  }

  async function regenImage(sb: Storyboard) {
    try {
      await editorApi.generateImage(sb.id as number, 1)
      toast.success('已提交重新生成任务')
    } catch {
      /* 拦截器已提示 */
    }
  }

  /* ---------------- 版本选定 / 编辑 / 删除 ---------------- */
  const [selectingKey, setSelectingKey] = useState<string | null>(null)

  async function selectVersion(v: ShotVersion & { shot_id?: number }) {
    if (!v.shot_id || !v.id) return
    const key = `${v.shot_id}-${v.id}`
    setSelectingKey(key)
    try {
      await editorApi.selectVersion(v.shot_id, v.id)
      toast.success('已选定该版本')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setSelectingKey(null)
    }
  }

  const [verEdit, setVerEdit] = useState<VersionEditState | null>(null)
  const [verSaving, setVerSaving] = useState(false)

  function openEditVersion(v: ShotVersion & { shot_id?: number }) {
    if (!v.shot_id || !v.id) return
    setVerEdit({
      shotId: v.shot_id,
      versionId: v.id,
      prompt: (v.prompt as string) || '',
      seed: (v.seed as number | null) ?? null
    })
  }

  async function saveVersion() {
    if (!verEdit) return
    setVerSaving(true)
    const payload: { prompt: string; seed?: number } = { prompt: verEdit.prompt }
    if (verEdit.seed !== null && verEdit.seed !== undefined) payload.seed = Number(verEdit.seed)
    try {
      await editorApi.updateVersion(verEdit.shotId, verEdit.versionId, payload)
      setVerEdit(null)
      toast.success('版本已更新')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setVerSaving(false)
    }
  }

  async function delVersion(sb: Storyboard, v: ShotVersion & { shot_id?: number }) {
    if (!v.shot_id || !v.id) return
    const isOn = selectedOf(sb)?.id === v.id
    const ok = await confirmDialog({
      title: '删除版本',
      content: isOn
        ? '该版本已被选定，删除后镜头的选定状态将被清空，确定删除吗？'
        : '确定删除该画面版本吗？',
      okText: '删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    try {
      await editorApi.deleteVersion(v.shot_id, v.id)
      toast.success('版本已删除')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    }
  }

  async function genVideo(sb: Storyboard) {
    const targets = selectedShots(sb)
    if (!targets.length) {
      toast.warning('请先选定一个画面版本')
      return
    }
    try {
      for (const sh of targets) {
        await editorApi.generateVideo(sh.id as number)
      }
      toast.success('已提交视频生成任务')
    } catch {
      /* 拦截器已提示 */
    }
  }

  const selectedCount = batchSel.size

  const cards = useMemo(
    () =>
      storyboards.map((sb, i) => {
        const versions = versionsOf(sb)
        const vsrc = versions.map((v) => imgOf(v as Record<string, unknown>)).filter(Boolean)
        return { sb, i, versions, vsrc, thumb: thumbOf(sb), video: videoUrlOf(sb) }
      }),
    [storyboards]
  )

  return (
    <section className="ed-section">
      <div className="ed-step-header">
        <div className="ed-step-badge">
          <span className="ed-step-sub">{storyboards.length} 幕 · 抽卡选定后可生成视频</span>
        </div>
        {storyboards.length > 0 && (
          <div className="ed-step-ops">
            <Button
              size="small"
              shape="round"
              type={batchMode ? 'primary' : 'default'}
              onClick={toggleBatchMode}
            >
              {batchMode ? '退出批量' : '批量模式'}
            </Button>
            {batchMode && (
              <>
                <Button size="small" type="link" onClick={selectAll}>
                  全选
                </Button>
                <span className="batch-count mono">已选 {selectedCount}</span>
                <Button
                  size="small"
                  type="primary"
                  disabled={!selectedCount}
                  onClick={() => setBatchImageOpen(true)}
                >
                  批量出图
                </Button>
                <Button
                  size="small"
                  type="primary"
                  ghost
                  disabled={!selectedCount}
                  onClick={() => setBatchVideoOpen(true)}
                >
                  批量出视频
                </Button>
              </>
            )}
          </div>
        )}
      </div>

      {storyboards.length ? (
        <div className="shot-grid">
          {cards.map(({ sb, i, versions, vsrc, thumb, video }) => {
            const id = sb.id as number
            const picked = batchSel.has(id)
            const duration = fmtDuration(sb.duration as number)
            return (
              <div key={String(id ?? i)} className={picked ? 'shot-card picked' : 'shot-card'}>
                <div className="shot-visual">
                  {batchMode && (
                    <label className="shot-check" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={picked}
                        aria-label={`选择第 ${i + 1} 幕`}
                        onChange={() => toggleBatchSel(id)}
                      />
                    </label>
                  )}

                  {thumb ? (
                    <Image
                      className="shot-img"
                      src={thumb}
                      alt={`第 ${i + 1} 镜缩略图`}
                      preview={vsrc.length ? { src: thumb } : false}
                    />
                  ) : (
                    <div className="shot-grad" style={{ background: gradVarOf(id ?? i) }}>
                      {i + 1}
                    </div>
                  )}

                  {hasSelected(sb) && (
                    <span className="sel" aria-label="已选定画面">
                      ✓
                    </span>
                  )}
                  {(sb.shot_type || duration) && (
                    <Tag className="qc" color="blue">
                      {(sb.shot_type as string) || duration}
                    </Tag>
                  )}
                </div>

                <div className="shot-info">
                  <div className="name">
                    第 {i + 1} 幕
                    {duration && <span className="n-meta mono num">{duration}</span>}
                  </div>
                  <div className="prompt">{(sb.description as string) || '（暂无画面描述）'}</div>
                  <div className={`s-dialogue${sb.dialogue ? '' : ' none'}`}>
                    {(sb.dialogue as string) || '（无台词）'}
                  </div>
                </div>

                {(versions.length > 0 || video) && (
                  <div className="shot-versions">
                    {versions.map((v, vi) => {
                      const on = selectedOf(sb)?.id === v.id
                      const key = `${v.shot_id}-${v.id}-${vi}`
                      return (
                        <div key={key} className="ver-cell">
                          <Image
                            className={on ? 'shot-ver on' : 'shot-ver'}
                            src={imgOf(v as Record<string, unknown>)}
                            alt={`第 ${i + 1} 镜候选画面 ${vi + 1}`}
                            preview={{ src: imgOf(v as Record<string, unknown>) }}
                          />
                          <div className="ver-ops">
                            {on ? (
                              <Tag color="success">已选</Tag>
                            ) : (
                              <Button
                                type="link"
                                size="small"
                                loading={selectingKey === `${v.shot_id}-${v.id}`}
                                onClick={() => void selectVersion(v)}
                              >
                                选定
                              </Button>
                            )}
                            <Button type="link" size="small" onClick={() => openEditVersion(v)}>
                              编辑
                            </Button>
                            <Button
                              type="link"
                              size="small"
                              danger
                              onClick={() => void delVersion(sb, v)}
                            >
                              删除
                            </Button>
                          </div>
                        </div>
                      )
                    })}

                    {video && (
                      <div className="ver-video">
                        <video src={video} controls preload="metadata" />
                        <span className="v-label">镜头视频</span>
                      </div>
                    )}
                  </div>
                )}

                <div className="shot-actions">
                  <Button
                    size="small"
                    type="primary"
                    icon={<PictureOutlined />}
                    onClick={() => openGenImage(sb)}
                  >
                    生成画面
                  </Button>
                  {versions.length > 0 && (
                    <Button size="small" onClick={() => void regenImage(sb)}>
                      重新生成
                    </Button>
                  )}
                  {hasSelected(sb) && !video && (
                    <Button
                      size="small"
                      type="primary"
                      ghost
                      icon={<VideoCameraOutlined />}
                      onClick={() => void genVideo(sb)}
                    >
                      生成视频
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="g-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先生成剧本，再来制作画面" />
        </div>
      )}

      {/* 单镜生成画面 */}
      <Modal
        title="生成画面"
        open={genOpen}
        width={380}
        okText="提交"
        cancelText="取消"
        confirmLoading={generating}
        onOk={confirmGen}
        onCancel={() => setGenOpen(false)}
      >
        <p className="dlg-hint">抽卡数量（每次生成 1 个版本，多版本便于对比挑选）</p>
        <InputNumber
          min={1}
          max={6}
          value={genCount}
          onChange={(v) => setGenCount(Number(v) || 1)}
          style={{ width: '100%' }}
        />
      </Modal>

      {/* 批量出图 */}
      <Modal
        title="批量生成画面"
        open={batchImageOpen}
        width={420}
        okText="提交"
        cancelText="取消"
        confirmLoading={batchSubmitting}
        onOk={confirmBatchImages}
        onCancel={() => setBatchImageOpen(false)}
      >
        <p className="dlg-hint">已选 {selectedCount} 个分镜，每个分镜生成的候选数量：</p>
        <InputNumber
          min={1}
          max={6}
          value={batchImageCount}
          onChange={(v) => setBatchImageCount(Number(v) || 1)}
          style={{ width: '100%' }}
        />
      </Modal>

      {/* 批量出视频 */}
      <Modal
        title="批量生成视频"
        open={batchVideoOpen}
        width={420}
        okText="提交"
        cancelText="取消"
        confirmLoading={batchSubmitting}
        onOk={confirmBatchVideos}
        onCancel={() => setBatchVideoOpen(false)}
      >
        <p className="dlg-hint">
          已选 {selectedCount} 个分镜。无选定画面或已有视频的分镜会被自动跳过。
        </p>
        <Select
          value={batchVideoSeconds}
          onChange={setBatchVideoSeconds}
          style={{ width: '100%' }}
          options={[
            { value: '5', label: '5 秒' },
            { value: '10', label: '10 秒' }
          ]}
        />
      </Modal>

      {/* 版本编辑 */}
      <Modal
        title="编辑画面版本"
        open={!!verEdit}
        width={480}
        okText="保存"
        cancelText="取消"
        confirmLoading={verSaving}
        onOk={saveVersion}
        onCancel={() => setVerEdit(null)}
      >
        <p className="dlg-hint">提示词</p>
        <Input.TextArea
          rows={4}
          value={verEdit?.prompt ?? ''}
          onChange={(e) => setVerEdit((p) => (p ? { ...p, prompt: e.target.value } : p))}
        />
        <p className="dlg-hint" style={{ marginTop: 12 }}>
          随机种子（留空表示不修改）
        </p>
        <InputNumber
          min={-1}
          max={999}
          value={verEdit?.seed ?? undefined}
          onChange={(v) => setVerEdit((p) => (p ? { ...p, seed: v === null ? null : Number(v) } : p))}
          style={{ width: '100%' }}
          placeholder="0-999"
        />
      </Modal>
    </section>
  )
}