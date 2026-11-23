/** 工作台：hero 统计 + 搜索/筛选 + 项目网格。 */
import { SearchOutlined } from '@ant-design/icons'
import { Button, Input, Spin } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { projectsApi } from '@/api/projects'
import { ProjectCard } from '@/components/ProjectCard'
import type { Project } from '@/types'

const FILTER_CHIPS = [
  { value: '', label: '全部' },
  { value: 'draft', label: '待开始' },
  { value: 'producing', label: '进行中' },
  { value: 'completed', label: '已完成' }
]

const IN_PROGRESS = ['draft', 'script_ready', 'producing']

export function Workspace() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setProjects(await projectsApi.list({ page: 1, page_size: 100 }))
    } catch {
      /* 错误提示由拦截器统一处理 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // 对应 Vue 的 computed(filtered)，这里用 useMemo 保持同一语义
  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    return projects.filter((p) => {
      if (status && p.status !== status) return false
      if (!kw) return true
      return [p.title, p.genre, p.style].some((f) =>
        String(f || '').toLowerCase().includes(kw)
      )
    })
  }, [projects, keyword, status])

  const stats = useMemo(
    () => ({
      total: projects.length,
      inProgress: projects.filter((p) => IN_PROGRESS.includes(p.status || '')).length,
      completed: projects.filter((p) => p.status === 'completed').length
    }),
    [projects]
  )

  function onDeleted(id: number) {
    setProjects((prev) => prev.filter((p) => p.id !== id))
  }

  return (
    <div className="g-page">
      <section className="home-hero">
        <div className="hero-left">
          <h1>AI 漫剧工作台</h1>
          <p>从一个创意到一部漫剧，AI 全流程为你代工</p>
          <div className="home-stats">
            <div className="home-stat">
              <b>{stats.total}</b>
              <span>项目总数</span>
            </div>
            <div className="home-stat">
              <b>{stats.inProgress}</b>
              <span>进行中</span>
            </div>
            <div className="home-stat">
              <b>{stats.completed}</b>
              <span>已完成</span>
            </div>
          </div>
        </div>
      </section>

      <div className="toolbar">
        <div className="search-box">
          <SearchOutlined className="search-icon" />
          <Input
            value={keyword}
            allowClear
            placeholder="搜索项目标题 / 题材 / 风格"
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        <div className="chip-row" role="group" aria-label="按状态筛选">
          {FILTER_CHIPS.map((c) => (
            <button
              key={c.value}
              type="button"
              className={status === c.value ? 'filter-chip on' : 'filter-chip'}
              onClick={() => setStatus(c.value)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid-wrap">
        {loading ? (
          <div className="grid-loading">
            <Spin size="large" />
          </div>
        ) : filtered.length ? (
          <div className="grid">
            {filtered.map((p, i) => (
              <ProjectCard
                key={p.id}
                project={p}
                delay={Math.min(i + 1, 6)}
                onDeleted={onDeleted}
              />
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
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
            </svg>
            <h3>暂无项目</h3>
            <p>点击右上角「新建」开始你的第一个漫剧</p>
            <Button type="primary" shape="round" onClick={() => navigate('/create')}>
              开始创作
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}