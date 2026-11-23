/** 编辑器数据接口（复刻 Editor.vue 的 loadAll 取数路径，含历史兜底）。 */
import api, { unwrap } from '@/api/client'
import { asList } from '@/lib/format'
import type {
  Asset,
  Character,
  Episode,
  PipelineSteps,
  ProjectDetailResponse,
  Storyboard,
  Timeline,
  TimelineItem
} from '@/types'

export interface EditorRawData {
  project: ProjectDetailResponse['project'] | null
  episodes: Episode[]
  storyboards: Storyboard[]
  characters: Character[]
  assets: Asset[]
  timelines: Timeline[]
}

export interface StoryboardPayload {
  shot_size: string
  scene: string
  dialogue: string
  emotion: string
  duration_sec: number
  episode_id?: number
}

export interface CharacterPayload {
  name: string
  description: string
  prompt_template: string
  voice: string
}

export const editorApi = {
  /** 项目详情：分镜列表缺失时回落到独立接口（原版行为一致） */
  async loadProject(projectId: string | number): Promise<EditorRawData> {
    const detail = unwrap<ProjectDetailResponse>(await api.get(`/projects/${projectId}`)) || {}

    const project = detail.project ?? (detail as unknown as ProjectDetailResponse['project'])
    const episodes = asList<Episode>(detail.episodes ?? [], 'episodes', 'list', 'items')

    let sbs = asList<Storyboard>(
      detail.storyboards ?? detail.project?.storyboards ?? [],
      'storyboards',
      'list',
      'items'
    )
    if (!sbs.length) {
      try {
        const r = unwrap<unknown>(await api.get(`/projects/${projectId}/storyboards`))
        sbs = asList<Storyboard>(r, 'storyboards', 'list', 'items')
      } catch {
        /* 无独立分镜接口时忽略 */
      }
    }

    let chars = asList<Character>(detail.characters ?? [], 'characters', 'list', 'items')
    try {
      const r = unwrap<unknown>(await api.get('/characters', { params: { project_id: projectId } }))
      const fromApi = asList<Character>(r, 'characters', 'list', 'items')
      if (fromApi.length) chars = fromApi
    } catch {
      /* 忽略 */
    }

    return {
      project: project ?? null,
      episodes,
      storyboards: sbs,
      characters: chars,
      assets: asList<Asset>(detail.assets ?? [], 'assets', 'list', 'items'),
      timelines: asList<Timeline>(detail.timelines ?? [], 'timelines', 'list', 'items')
    }
  },

  /** 流水线状态：失败时返回 null，由调用方回落到本地推导 */
  async loadPipeline(episodeId: number): Promise<PipelineSteps | null> {
    try {
      const r = unwrap<{ steps?: PipelineSteps }>(
        await api.get(`/episodes/${episodeId}/pipeline-status`)
      )
      return r?.steps ?? null
    } catch {
      return null
    }
  },

  retryTask(taskId: number | string) {
    return api.post(`/tasks/${taskId}/retry`)
  },

  cancelTask(taskId: number | string) {
    return api.post(`/tasks/${taskId}/cancel`)
  },

  /* ---------------- 剧本分区 ---------------- */

  /** 无剧集时回退项目级入口（与原版一致） */
  generateScript(projectId: string | number, episodeId: number | null) {
    const path = episodeId
      ? `/episodes/${episodeId}/generate-script`
      : `/projects/${projectId}/generate-script`
    return api.post(path)
  },

  extractCharacters(episodeId: number) {
    return api
      .post(`/episodes/${episodeId}/extract-characters`)
      .then((res) => unwrap<{ created?: number; updated?: number }>(res))
  },

  saveSynopsis(episodeId: number, synopsis: string) {
    return api.put(`/episodes/${episodeId}`, { synopsis })
  },

  createStoryboard(projectId: string | number, payload: StoryboardPayload) {
    return api.post(`/projects/${projectId}/storyboards`, payload)
  },

  updateStoryboard(storyboardId: number, payload: StoryboardPayload) {
    return api.put(`/storyboards/${storyboardId}`, payload)
  },

  deleteStoryboard(storyboardId: number) {
    return api.delete(`/storyboards/${storyboardId}`)
  },

  reorderStoryboards(projectId: string | number, orderedIds: Array<number | undefined>) {
    return api.put(`/projects/${projectId}/storyboards/reorder`, { ordered_ids: orderedIds })
  },

  /* ---------------- 角色分区 ---------------- */

  createCharacter(projectId: string | number, payload: CharacterPayload) {
    return api
      .post(`/projects/${projectId}/characters`, payload)
      .then((res) => unwrap<Character>(res))
  },

  updateCharacter(characterId: number, payload: CharacterPayload) {
    return api.put(`/characters/${characterId}`, payload)
  },

  deleteCharacter(characterId: number) {
    return api.delete(`/characters/${characterId}`)
  },

  generateRef(characterId: number) {
    return api.post(`/characters/${characterId}/generate-ref`)
  },

  /** 返回值兼容字符串或 {audio_url}/{url} 三种形态（原版同样做了兜底） */
  audition(characterId: number) {
    return api.get(`/characters/${characterId}/audition`).then((res) => unwrap<unknown>(res))
  },

  /* ---------------- 配音分区 ---------------- */

  generateVoice(storyboardId: number, payload: { character_id?: number; voice?: string }) {
    return api.post(`/storyboards/${storyboardId}/generate-voice`, payload)
  },

  /* ---------------- 画面分镜分区 ---------------- */

  batchImages(episodeId: number, payload: { storyboard_ids: number[]; count: number }) {
    return api
      .post(`/episodes/${episodeId}/batch-images`, payload)
      .then((res) => unwrap<{ submitted?: number }>(res))
  },

  batchVideos(episodeId: number, payload: { storyboard_ids: number[]; seconds: string }) {
    return api
      .post(`/episodes/${episodeId}/batch-videos`, payload)
      .then((res) => unwrap<{ submitted?: number; skipped?: unknown[] }>(res))
  },

  generateImage(storyboardId: number, count: number) {
    return api.post(`/storyboards/${storyboardId}/generate-image`, { count })
  },

  selectVersion(shotId: number, versionId: number) {
    return api.post(`/shots/${shotId}/select-version`, { version_id: versionId })
  },

  updateVersion(shotId: number, versionId: number, payload: { prompt: string; seed?: number }) {
    return api.put(`/shots/${shotId}/versions/${versionId}`, payload)
  },

  deleteVersion(shotId: number, versionId: number) {
    return api.delete(`/shots/${shotId}/versions/${versionId}`)
  },

  generateVideo(shotId: number) {
    return api.post(`/shots/${shotId}/generate-video`)
  },

  /* ---------------- 成片分区 ---------------- */

  createTimeline(projectId: string | number, episodeId: number | null) {
    return api.post(`/projects/${projectId}/timelines`, { episode_id: episodeId })
  },

  saveTimeline(timelineId: number, items: TimelineItem[]) {
    return api.put(`/timelines/${timelineId}`, {
      items: items.map((it) => ({
        shot_id: it.shot_id,
        version_id: it.version_id,
        media_url: it.media_url || (it as { image_url?: string }).image_url,
        duration_sec: Number(it.duration) || 5,
        subtitle: it.subtitle,
        audio_url: it.audio_url
      }))
    })
  },

  deleteTimeline(timelineId: number) {
    return api.delete(`/timelines/${timelineId}`)
  },

  composite(timelineId: number) {
    return api.post(`/timelines/${timelineId}/composite`)
  },

  /** 合成预检：返回缺失镜头视频的清单（失败返回 null，不阻断合成） */
  async compositeCheck(episodeId: number | null) {
    if (!episodeId) return null
    try {
      return await api
        .get(`/episodes/${episodeId}/composite-check`)
        .then((res) => unwrap<{ total?: number; missing?: Array<{ seq: number | string }> }>(res))
    } catch {
      return null
    }
  },

  exportFinal(projectId: string | number, episodeId: number | null) {
    return api
      .get(`/projects/${projectId}/export`, { params: episodeId ? { episode_id: episodeId } : {} })
      .then((res) => unwrap<{ output_url?: string }>(res))
  }
}