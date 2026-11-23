/**
 * 导演工作台（Editor）——迁移骨架。
 *
 * 已迁移：数据加载（剧集/分镜/角色/素材/时间线）、pipeline 三态推导、
 *         SSE 任务流与失败聚合提示、剧集切换、刷新。
 * 待迁移：五个分区的内容 UI 与 6 个弹窗（见 docs/editor-migration-assessment.md）。
 */
import { ReloadOutlined } from '@ant-design/icons'
import { Button, Select, Spin } from 'antd'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { useEditorData } from '@/hooks/useEditorData'
import { useTaskStream } from '@/hooks/useTaskStream'
import { ScriptTab } from '@/components/editor/ScriptTab'
import { CharacterTab } from '@/components/editor/CharacterTab'
import { BoardTab } from '@/components/editor/BoardTab'
import { FinalTab } from '@/components/editor/FinalTab'
import { TaskProgress } from '@/components/TaskProgress'
import { VoiceTab } from '@/components/editor/VoiceTab'
import { assetTypeOf, hasSelected } from '@/lib/entities'

type StepKey = 'script' | 'character' | 'board' | 'voice' | 'final'

const STEPS: Array<{ key: StepKey; label: string; desc: string; icon: string }> = [
  { key: 'script', label: '剧本', desc: 'AI 生成分镜脚本', icon: '📝' },
  { key: 'character', label: '角色', desc: '形象与音色设定', icon: '🎭' },
  { key: 'board', label: '画面分镜', desc: '分镜编排 · 抽卡选定 · 视频', icon: '🎨' },
  { key: 'voice', label: '配音', desc: '台词语音合成', icon: '🎤' },
  { key: 'final', label: '成片', desc: '时间线与合成', icon: '🎬' }
]

const STEP_ORDER: StepKey[] = ['script', 'character', 'board', 'voice', 'final']

export function EditorPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const data = useEditorData(id)
  const [activeTab, setActiveTab] = useState<StepKey>('script')
  const tasks = useTaskStream(id, () => void data.loadAll())

  /* ---------------- 三态流水线：后端优先，本地兜底 ---------------- */
  const doneMap = useMemo(() => {
    const { storyboards, characters, assets, timelines, pipe } = data
    const localBoard = storyboards.some((sb) => (sb.shots || []).length > 0)
    const localImage = storyboards.length > 0 && storyboards.every((sb) => hasSelected(sb))
    const local: Record<StepKey, boolean> = {
      script: storyboards.length > 0,
      character: characters.length > 0,
      board: localBoard && localImage,
      voice: assets.some((a) => assetTypeOf(a as Record<string, unknown>) === 'audio'),
      final: timelines.some((t) => t.status === 'completed' && !!t.output_url)
    }
    const p = pipe
    if (!p) return local
    return {
      script: p.script?.status === 'done' || local.script,
      character: p.character?.status === 'done' || local.character,
      board:
        (p.board?.status === 'done' || localBoard) && (p.image?.status === 'done' || localImage),
      voice: p.voice?.status === 'done' || local.voice,
      final: p.final?.status === 'done' || local.final
    } as Record<StepKey, boolean>
  }, [data])

  function stepState(key: StepKey): 'done' | 'active' | 'pending' {
    if (doneMap[key]) return 'done'
    const p = data.pipe
    if (!p) return 'pending'
    const active = (k: string) => p[k]?.status === 'partial' || p[k]?.status === 'running'
    if (key === 'board' ? active('board') || active('image') : active(key)) return 'active'
    return 'pending'
  }

  /** 画面分镜步展示抽卡进度（后端 image 环节计数） */
  function stepCount(key: StepKey): string {
    const p = data.pipe
    const src = key === 'board' ? p?.image : p?.[key]
    if (src && typeof src.completed === 'number' && typeof src.total === 'number' && src.total > 0) {
      return `${src.completed}/${src.total}`
    }
    return ''
  }

  const doneCount = STEP_ORDER.filter((k) => doneMap[k]).length

  const activeStep = STEPS.find((s) => s.key === activeTab) ?? STEPS[0]

  if (data.refreshing && !data.project) {
    return (
      <div className="ed-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="editor-shell">
      {/* ---------------- 顶栏 ---------------- */}
      <header className="ed-topbar">
        <button type="button" className="ed-back" onClick={() => navigate('/')}>
          ← 返回
        </button>

        <div className="ed-title">
          <h1>{data.project?.title || '未命名项目'}</h1>
          <span className="ed-progress">完成 {doneCount}/{STEP_ORDER.length}</span>
        </div>

        <div className="ed-actions">
          {data.episodes.length > 0 && (
            <Select
              size="small"
              value={data.currentEpisodeId ?? undefined}
              style={{ minWidth: 160 }}
              placeholder="选择剧集"
              onChange={(v: number) => data.switchEpisode(v)}
              options={data.episodes.map((e) => ({
                value: e.id,
                label: `第${e.episode_number ?? 1}集 · ${e.title || '未命名'}`
              }))}
            />
          )}
          <TaskProgress tasks={tasks.taskList} onRetry={tasks.retry} onCancel={tasks.cancel} />
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={data.refreshing}
            onClick={() => void data.loadAll()}
          >
            刷新
          </Button>
        </div>
      </header>

      <div className="ed-body">
        {/* ---------------- 步骤导航 ---------------- */}
        <nav className="ed-steps" aria-label="制作步骤">
          {STEPS.map((s, i) => {
            const state = stepState(s.key)
            const count = stepCount(s.key)
            return (
              <button
                key={s.key}
                type="button"
                className={`ed-step${activeTab === s.key ? ' current' : ''} ${state}`}
                aria-current={activeTab === s.key ? 'step' : undefined}
                onClick={() => setActiveTab(s.key)}
              >
                <span className="ed-step-no">{String(i + 1).padStart(2, '0')}</span>
                <span className="ed-step-icon" aria-hidden="true">
                  {s.icon}
                </span>
                <span className="ed-step-text">
                  <strong>{s.label}</strong>
                  <em>{s.desc}</em>
                </span>
                {count && <span className="ed-step-count">{count}</span>}
                {state === 'done' && <span className="ed-step-done">✓</span>}
              </button>
            )
          })}
        </nav>

        {/* ---------------- 分区内容 ---------------- */}
        <main className="ed-main">
          <div className="ed-main-head">
            <h2>
              {activeStep.label}
              <small>{activeStep.desc}</small>
            </h2>
          </div>

          {activeTab === 'script' && (
            <ScriptTab
              projectId={id}
              episodeId={data.currentEpisodeId}
              episode={data.currentEpisode}
              storyboards={data.storyboards}
              onReload={data.loadAll}
            />
          )}
          {activeTab === 'character' && (
            <CharacterTab
              projectId={id}
              characters={data.characters}
              onReload={data.loadAll}
            />
          )}
          {activeTab === 'board' && (
            <BoardTab
              episodeId={data.currentEpisodeId}
              storyboards={data.storyboards}
              onReload={data.loadAll}
            />
          )}
          {activeTab === 'voice' && (
            <VoiceTab
              storyboards={data.storyboards}
              characters={data.characters}
              assets={data.assets}
            />
          )}
          {activeTab === 'final' && (
            <FinalTab
              projectId={id}
              episodeId={data.currentEpisodeId}
              timelines={data.timelines}
              onReload={data.loadAll}
            />
          )}
        </main>
      </div>
    </div>
  )
}