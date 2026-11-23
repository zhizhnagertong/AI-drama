/** 项目卡片：渐变占位封面 + 状态胶囊 + 二次确认删除。 */
import { DeleteOutlined } from '@ant-design/icons'
import { Input, Modal } from 'antd'
import { useRef, useState } from 'react'
import { Link } from 'react-router'

import { projectsApi } from '@/api/projects'
import { useReveal } from '@/hooks/useReveal'
import { confirmDialog, toast } from '@/lib/feedback'
import { dotClassOf, fmtTime, gradVar, statusText } from '@/lib/format'
import type { Project } from '@/types'

interface ProjectCardProps {
  project: Project
  /** 入场延迟 1-6 级（对应原 v-reveal="Math.min(i+1,6)"） */
  delay?: number
  onDeleted: (id: number) => void
}

export function ProjectCard({ project, delay = 0, onDeleted }: ProjectCardProps) {
  const cardRef = useRef<HTMLElement>(null)
  useReveal(cardRef, delay)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [input, setInput] = useState('')
  const [inputError, setInputError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const title = project.title || '未命名项目'
  const cover = project.cover_url || ''
  const styleName = project.style || project.style_name || '未指定风格'
  const timeText = fmtTime(project.updated_at || project.created_at)

  const rawChar =
    project.characters?.length ?? project.character_count ?? project.stats?.character_count
  const rawEp = project.episodes?.length ?? project.episode_count ?? project.stats?.storyboard_count
  const charCount = Number.isFinite(rawChar) ? (rawChar as number) : null
  const epCount = Number.isFinite(rawEp) ? (rawEp as number) : null

  /** 第一重确认：警告此操作不可恢复 */
  async function startDelete() {
    const ok = await confirmDialog({
      title: '删除项目',
      content: `确定删除项目「${title}」吗？该项目的所有剧集、分镜、生成图片与视频将被一并删除。`,
      okText: '继续删除',
      cancelText: '取消',
      danger: true
    })
    if (!ok) return
    setInput('')
    setInputError('')
    setConfirmOpen(true)
  }

  /** 第二重确认：输入项目名防止误删 */
  async function doDelete() {
    if (input.trim() !== title) {
      setInputError('项目名不匹配')
      return
    }
    setSubmitting(true)
    try {
      await projectsApi.remove(project.id)
      toast.success('项目已彻底删除')
      setConfirmOpen(false)
      onDeleted(project.id)
    } catch {
      /* 错误提示已由 axios 拦截器统一处理 */
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <article ref={cardRef} className="project-card g-card">
        <div className="project-thumb">
          {cover ? (
            <img src={cover} alt={`${title} 封面`} loading="lazy" width={640} height={360} />
          ) : (
            <div className="thumb-grad" style={{ background: gradVar(project.id) }}>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <path d="M3 8l4-4 5 5 4-4 5 5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
              </svg>
            </div>
          )}

          <div className="project-status">
            <span className="tag">
              <span className={`dot ${dotClassOf(project.status)}`} />
              {statusText(project.status)}
            </span>
          </div>

          <button
            type="button"
            className="project-more"
            title="删除项目"
            aria-label="删除项目"
            onClick={(e) => {
              e.stopPropagation()
              void startDelete()
            }}
          >
            <DeleteOutlined style={{ fontSize: 13 }} />
          </button>
        </div>

        <div className="project-body">
          <div className="project-name" title={title}>
            <Link className="title-link" to={`/project/${project.id}`}>
              {title}
            </Link>
          </div>
          <div className="project-meta">
            <span className="tag tag-primary">{styleName}</span>
            {charCount !== null && epCount !== null && (
              <span className="counts">
                {charCount}角色 · {epCount}集
              </span>
            )}
            {timeText && <span className="time">{timeText}</span>}
          </div>
        </div>
      </article>

      <Modal
        title="再次确认"
        open={confirmOpen}
        centered
        okText="彻底删除"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: submitting }}
        onOk={doDelete}
        onCancel={() => setConfirmOpen(false)}
        destroyOnHidden
      >
        <p className="delete-warn">
          此操作不可恢复！请输入项目名「<strong>{title}</strong>」以确认彻底删除。
        </p>
        <Input
          value={input}
          placeholder={title}
          status={inputError ? 'error' : undefined}
          onChange={(e) => {
            setInput(e.target.value)
            if (inputError) setInputError('')
          }}
          onPressEnter={doDelete}
        />
        {inputError && <p className="delete-error">{inputError}</p>}
      </Modal>
    </>
  )
}