/**
 * 成片分区（对应 Editor.vue 第 1443–1548 行 + 第 813–941 行逻辑）。
 *
 * 迁移要点：时间线的上移/下移/删除是「先在本地数组上改，再整条 PUT 保存」，
 * 原版直接改 reactive 数组；React 里必须维护一份本地 items 状态，
 * 否则 props 是不可变的，改了不生效。
 */
import { CheckOutlined, DeleteOutlined, DownloadOutlined, PlayCircleOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Button, Empty, Image, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useState } from 'react'

import { editorApi } from '@/api/editor'
import { confirmDialog, toast } from '@/lib/feedback'
import { fmtDuration } from '@/lib/entities'
import type { Timeline, TimelineItem } from '@/types'

interface FinalTabProps {
  projectId: string
  episodeId: number | null
  timelines: Timeline[]
  onReload: () => Promise<void> | void
}

export function FinalTab({ projectId, episodeId, timelines, onReload }: FinalTabProps) {
  /** 优先取「已完成且有成片」的时间线，否则取最后一条（与原版一致） */
  const timeline = useMemo(() => {
    if (!timelines.length) return null
    return (
      timelines.find((t) => t.status === 'completed' && !!t.output_url) ||
      timelines[timelines.length - 1]
    )
  }, [timelines])

  const [items, setItems] = useState<TimelineItem[]>([])
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [compositing, setCompositing] = useState(false)

  // props 变化（reload / 切换剧集）时以服务端为准重置本地顺序
  useEffect(() => {
    setItems(timeline?.items ?? [])
  }, [timeline])

  async function saveTimeline(next: TimelineItem[]) {
    if (!timeline) return
    try {
      await editorApi.saveTimeline(timeline.id, next)
    } catch {
      /* 拦截器已提示 */
    }
  }

  function moveTl(index: number, d: number) {
    const j = index + d
    if (j < 0 || j >= items.length) return
    const next = [...items]
    const tmp = next[index]
    next[index] = next[j]
    next[j] = tmp
    setItems(next)
    void saveTimeline(next)
  }

  function removeTl(index: number) {
    const next = items.filter((_, i) => i !== index)
    setItems(next)
    void saveTimeline(next)
  }

  async function autoTimeline() {
    setTimelineLoading(true)
    try {
      await editorApi.createTimeline(projectId, episodeId)
      toast.success('已提交时间线生成')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    } finally {
      setTimelineLoading(false)
    }
  }

  async function composite() {
    if (!timeline) return
    const check = await editorApi.compositeCheck(episodeId)
    if (check && check.missing && check.missing.length) {
      const seqs = check.missing.map((m) => m.seq).join('、')
      const ok = await confirmDialog({
        title: '合成预检',
        content: `${check.total} 幕中有 ${check.missing.length} 幕缺少镜头视频（第 ${seqs} 幕），时间线将自动跳过它们。是否继续合成？`,
        okText: '继续合成',
        cancelText: '取消'
      })
      if (!ok) return
    }
    setCompositing(true)
    try {
      await editorApi.composite(timeline.id)
      toast.success('已提交成片合成任务')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setCompositing(false)
    }
  }

  async function downloadFinal() {
    try {
      const r = await editorApi.exportFinal(projectId, episodeId)
      const url = r?.output_url || timeline?.output_url
      if (!url) {
        toast.warning('暂无可下载的成片')
        return
      }
      const a = document.createElement('a')
      a.href = url
      a.download = ''
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch {
      /* 拦截器已提示 */
    }
  }

  async function delTimeline() {
    if (!timeline) return
    const ok = await confirmDialog({
      title: '删除时间线',
      content: '确定删除当前时间线吗？',
      okText: '删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    try {
      await editorApi.deleteTimeline(timeline.id)
      toast.success('时间线已删除')
      await onReload()
    } catch {
      /* 拦截器已提示 */
    }
  }

  const columns: ColumnsType<TimelineItem> = [
    { title: '序号', width: 60, align: 'center', render: (_v, _r, i) => i + 1 },
    {
      title: '缩略图',
      width: 120,
      render: (_v, r) => (
        <div className="tl-thumb">
          {r.media_url ? (
            <Image src={r.media_url} alt="时间线缩略图" width={88} height={50} />
          ) : (
            <div className="tl-grad">—</div>
          )}
        </div>
      )
    },
    { title: '时长', width: 80, render: (_v, r) => fmtDuration(r.duration) || '-' },
    { title: '字幕', dataIndex: 'subtitle', ellipsis: true },
    {
      title: '音频',
      width: 70,
      align: 'center',
      render: (_v, r) =>
        r.audio_url ? <CheckOutlined style={{ color: 'var(--success)' }} /> : <span className="text-secondary">—</span>
    },
    {
      title: '操作',
      width: 170,
      fixed: 'right',
      render: (_v, _r, i) => (
        <div className="sb-ops">
          <Button type="link" size="small" disabled={i === 0} onClick={() => moveTl(i, -1)}>
            上移
          </Button>
          <Button
            type="link"
            size="small"
            disabled={i === items.length - 1}
            onClick={() => moveTl(i, 1)}
          >
            下移
          </Button>
          <Button type="link" size="small" danger onClick={() => removeTl(i)}>
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
          <span className="ed-step-sub">
            {timeline ? `时间线 ${items.length} 项` : '未创建时间线'}
            {timeline?.status && (
              <Tag style={{ marginLeft: 8 }} color={timeline.output_url ? 'success' : 'default'}>
                {timeline.output_url ? '已合成' : timeline.status}
              </Tag>
            )}
          </span>
        </div>
        <div className="ed-step-ops">
          <Button
            size="small"
            icon={<UnorderedListOutlined />}
            loading={timelineLoading}
            onClick={() => void autoTimeline()}
          >
            自动生成时间线
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            disabled={!timeline || !items.length}
            loading={compositing}
            onClick={() => void composite()}
          >
            合成成片
          </Button>
          <Button
            size="small"
            danger
            ghost
            icon={<DeleteOutlined />}
            disabled={!timeline}
            onClick={() => void delTimeline()}
          >
            删除时间线
          </Button>
        </div>
      </div>

      {timeline ? (
        <>
          {timeline.output_url && (
            <div className="output">
              <div className="video-frame">
                <video
                  src={timeline.output_url as string}
                  controls
                  preload="metadata"
                  className="final-video"
                />
              </div>
              <div className="out-ops">
                <Button type="primary" icon={<DownloadOutlined />} onClick={() => void downloadFinal()}>
                  下载成片
                </Button>
              </div>
            </div>
          )}

          <div className="timeline-panel">
            <div className="tl-label">镜头序列</div>
            <div className="table-card">
              <Table<TimelineItem>
                dataSource={items}
                columns={columns}
                rowKey={(r) => String(r.id)}
                pagination={false}
                size="small"
                scroll={{ x: 720 }}
              />
            </div>
          </div>
        </>
      ) : (
        <div className="g-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="先「自动生成时间线」，再「合成成片」"
          />
        </div>
      )}
    </section>
  )
}