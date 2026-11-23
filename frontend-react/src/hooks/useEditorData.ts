/**
 * 编辑器取数（移植自 Editor.vue 的 loadAll / loadPipeline / switchEpisode）。
 *
 * 与 Vue 版的差异：currentEpisodeId 同时用 state（驱动渲染）和 ref（供异步流程读取最新值），
 * 避免把 currentEpisodeId 放进 useCallback 依赖里导致 loadAll 每次切换都换身份、
 * 进而触发重新取数的循环。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import { editorApi } from '@/api/editor'
import { normStoryboard, normTimeline } from '@/lib/entities'
import { useProjectStore } from '@/store/project'
import type {
  Asset,
  Character,
  Episode,
  PipelineSteps,
  Project,
  Storyboard,
  Timeline
} from '@/types'

interface Lo {
  [key: string]: unknown
}

export interface EditorData {
  project: Project | null
  episodes: Episode[]
  currentEpisodeId: number | null
  currentEpisode: Episode | null
  storyboards: Storyboard[]
  characters: Character[]
  assets: Asset[]
  timelines: Timeline[]
  pipe: PipelineSteps | null
  refreshing: boolean
  loadAll: () => Promise<void>
  switchEpisode: (id: number) => void
  reloadPipeline: () => Promise<void>
}

export function useEditorData(projectId: string): EditorData {
  const [project, setProject] = useState<Project | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [currentEpisodeId, setCurrentEpisodeId] = useState<number | null>(null)
  const [storyboards, setStoryboards] = useState<Storyboard[]>([])
  const [characters, setCharacters] = useState<Character[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [timelines, setTimelines] = useState<Timeline[]>([])
  const [pipe, setPipe] = useState<PipelineSteps | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const episodeIdRef = useRef<number | null>(null)
  const [searchParams] = useSearchParams()

  const loadAll = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await editorApi.loadProject(projectId)
      setProject(data.project ?? null)
      setEpisodes(data.episodes)

      // 首次进入：?episode= 优先，其次第一集；已选剧集失效时回落到第一集
      let epId = episodeIdRef.current
      if (!epId) {
        const q = Number(searchParams.get('episode'))
        epId = data.episodes.find((e) => e.id === q)?.id ?? data.episodes[0]?.id ?? null
      } else if (!data.episodes.some((e) => e.id === epId)) {
        epId = data.episodes[0]?.id ?? null
      }
      episodeIdRef.current = epId
      setCurrentEpisodeId(epId)

      // 按当前集过滤（历史数据 episode_id 为空时归入第一集展示）
      const sbs = epId
        ? data.storyboards.filter((sb) => !sb.episode_id || sb.episode_id === epId)
        : data.storyboards
      const normalizedSb = sbs.map((sb, i) => normStoryboard(sb as Lo, i))
      setStoryboards(normalizedSb)
      setCharacters(data.characters)
      setAssets(data.assets)

      const tls = epId
        ? data.timelines.filter((t) => !t.episode_id || t.episode_id === epId)
        : data.timelines
      const normalizedTl = tls.map((t) => normTimeline(t as Lo))
      setTimelines(normalizedTl)

      useProjectStore.getState().setAll({
        project: data.project ?? null,
        storyboards: normalizedSb,
        characters: data.characters,
        assets: data.assets,
        timelines: normalizedTl
      })

      setPipe(epId ? await editorApi.loadPipeline(epId) : null)
    } finally {
      setRefreshing(false)
    }
  }, [projectId, searchParams])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const switchEpisode = useCallback(
    (id: number) => {
      if (id === episodeIdRef.current) return
      episodeIdRef.current = id
      setCurrentEpisodeId(id)
      void loadAll()
    },
    [loadAll]
  )

  const reloadPipeline = useCallback(async () => {
    const epId = episodeIdRef.current
    setPipe(epId ? await editorApi.loadPipeline(epId) : null)
  }, [])

  const currentEpisode = useMemo(
    () => episodes.find((e) => e.id === currentEpisodeId) || null,
    [episodes, currentEpisodeId]
  )

  return {
    project,
    episodes,
    currentEpisodeId,
    currentEpisode,
    storyboards,
    characters,
    assets,
    timelines,
    pipe,
    refreshing,
    loadAll,
    switchEpisode,
    reloadPipeline
  }
}