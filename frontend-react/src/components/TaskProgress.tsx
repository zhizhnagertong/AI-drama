/**
 * 生成任务进度面板（对应 Vue 版 components/TaskProgress.vue 398 行）。
 *
 * 原版用 <Teleport to="body"> 把展开面板传送到 body，避免被顶栏的
 * backdrop-filter 堆叠上下文裁切；React 用 createPortal 等价实现。
 */
import { Progress } from 'antd'
import { createPortal } from 'react-dom'
import { useMemo, useState } from 'react'

import { taskStatusTag, taskStatusText, taskTypeLabel } from '@/lib/entities'
import type { TaskInfo } from '@/types'

interface TaskProgressProps {
  tasks: Array<TaskInfo & { status?: string }>
  onRetry: (t: TaskInfo) => void
  onCancel: (t: TaskInfo) => void
}

const WEIGHT: Record<string, number> = {
  running: 0,
  processing: 0,
  pending: 1,
  failed: 2,
  succeeded: 3
}

const CANCELABLE = ['pending', 'queued', 'running', 'processing']

const TAG_CLASS: Record<string, string> = {
  primary: 'tag-primary',
  success: 'tag-success',
  warning: 'tag-warning',
  danger: 'tag-danger'
}

/** 状态 → 语义色类名（对应原版 taskStatusTag 的 primary/success/warning/danger） */
function tagClass(status?: string): string {
  return TAG_CLASS[taskStatusTag(status)] || ''
}

function pct(t: TaskInfo): number {
  const p = Number(t.progress)
  if (t.status === 'succeeded') return 100
  if (!Number.isFinite(p)) return t.status === 'running' || t.status === 'processing' ? 50 : 0
  return Math.max(0, Math.min(100, Math.round(p * (p <= 1 ? 100 : 1))))
}

export function TaskProgress({ tasks, onRetry, onCancel }: TaskProgressProps) {
  const [open, setOpen] = useState(false)

  const sorted = useMemo(() => {
    const list = tasks.filter((t) => t && (t.task_id || (t as { id?: number }).id))
    return [...list].sort((a, b) => (WEIGHT[a.status || ''] ?? 4) - (WEIGHT[b.status || ''] ?? 4))
  }, [tasks])

  const activeCount = sorted.filter((t) => CANCELABLE.includes(t.status || '')).length
  const failedCount = sorted.filter((t) => t.status === 'failed').length
  const doneCount = sorted.filter((t) => t.status === 'succeeded').length
  /** 面板只展示进行中/失败任务，已完成项折叠为计数，避免长列表遮挡页面 */
  const visibleTasks = sorted.filter((t) => t.status !== 'succeeded')

  if (!sorted.length) return null

  const summaryText = activeCount
    ? `生成中 ${activeCount}`
    : failedCount
      ? `失败 ${failedCount}`
      : `已完成 ${doneCount}`

  return (
    <div className="tp-wrap">
      <button
        type="button"
        className="tp-summary"
        aria-expanded={open}
        aria-label="展开或收起生成任务面板"
        onClick={() => setOpen((v) => !v)}
      >
        {activeCount ? (
          <span className="tp-spinner" aria-hidden="true" />
        ) : (
          <span className={failedCount ? 'tp-dot tp-dot--err' : 'tp-dot'} aria-hidden="true" />
        )}
        <span className="tp-summary-text">{summaryText}</span>
        <svg
          className={`tp-chevron${open ? ' open' : ''}`}
          aria-hidden="true"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open &&
        createPortal(
          <div className="task-progress" aria-live="polite" aria-label="生成任务进度">
            <div className="tp-panel-head">
              <span className="tp-panel-title">生成任务</span>
              <button
                type="button"
                className="link-btn"
                aria-label="收起任务面板"
                onClick={() => setOpen(false)}
              >
                收起
              </button>
            </div>

            {visibleTasks.map((t) => (
              <div key={String(t.task_id)} className="task-item">
                <div className="row">
                  <span className={`tag ${tagClass(t.status)}`}>{taskStatusText(t.status)}</span>
                  <span className="type" title={taskTypeLabel(t.type)}>
                    {taskTypeLabel(t.type)}
                  </span>
                  {t.status === 'failed' && (
                    <button type="button" className="link-btn retry-btn" onClick={() => onRetry(t)}>
                      重试
                    </button>
                  )}
                  {CANCELABLE.includes(t.status || '') && (
                    <button type="button" className="link-btn cancel-btn" onClick={() => onCancel(t)}>
                      取消
                    </button>
                  )}
                </div>
                {t.status !== 'failed' ? (
                  <Progress
                    percent={pct(t)}
                    status={t.status === 'succeeded' ? 'success' : 'active'}
                    showInfo={false}
                    strokeWidth={4}
                    size="small"
                  />
                ) : (
                  <div className="err" title={t.error || '生成失败'}>
                    {t.error || '生成失败'}
                  </div>
                )}
              </div>
            ))}

            {doneCount > 0 && (
              <div className="task-item done-row">
                <span className="tag tag-success">已完成</span>
                <span className="type">共 {doneCount} 项任务</span>
              </div>
            )}
            {!visibleTasks.length && (
              <div className="task-item">
                <span className="type">当前没有进行中的任务</span>
              </div>
            )}
          </div>,
          document.body
        )}
    </div>
  )
}