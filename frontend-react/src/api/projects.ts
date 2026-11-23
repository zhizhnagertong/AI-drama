import api, { unwrap } from '@/api/client'
import { asList } from '@/lib/format'
import type { Asset, Episode, Project, Storyboard, TaskInfo } from '@/types'

export interface ProjectUpdatePayload {
  title?: string
  genre?: string
  style?: string
  aspect_ratio?: string
  cover_url?: string
  status?: string
}

export interface ProjectDetailData {
  project: Project
  episodes: Episode[]
  storyboards: Storyboard[]
  assets: Asset[]
}

export const projectsApi = {
  async list(params: { page?: number; page_size?: number } = { page: 1, page_size: 100 }) {
    const res = await api.get('/projects', { params })
    return asList<Project>(unwrap<unknown>(res), 'projects', 'list')
  },

  /** 项目详情：/projects/{id} 返回扁平对象（字段与 project 同级），这里兼容两种形态 */
  async detail(id: string | number): Promise<ProjectDetailData> {
    const raw = unwrap<Record<string, unknown>>(await api.get(`/projects/${id}`)) || {}
    const project = (raw.project ?? raw) as Project
    return {
      project,
      episodes: asList<Episode>(raw.episodes ?? [], 'episodes', 'list', 'items'),
      storyboards: asList<Storyboard>(raw.storyboards ?? [], 'storyboards', 'list', 'items'),
      assets: asList<Asset>(raw.assets ?? [], 'assets', 'list', 'items')
    }
  },

  async update(id: string | number, payload: ProjectUpdatePayload) {
    return api.put(`/projects/${id}`, payload)
  },

  async remove(id: number) {
    await api.delete(`/projects/${id}`)
  },

  /** 生成封面：返回 task_id，需轮询 /tasks/{id} */
  async generateCover(id: string | number) {
    return unwrap<{ task_id: number }>(await api.post(`/projects/${id}/generate-cover`))
  },

  async getTask(taskId: number) {
    return unwrap<TaskInfo>(await api.get(`/tasks/${taskId}`))
  },

  /* ---------------- 剧集 ---------------- */

  async createEpisode(projectId: string | number, payload: { title?: string; synopsis?: string }) {
    return api.post(`/projects/${projectId}/episodes`, payload)
  },

  async updateEpisode(episodeId: number, payload: { title?: string; synopsis?: string }) {
    return api.put(`/episodes/${episodeId}`, payload)
  },

  async removeEpisode(episodeId: number) {
    return api.delete(`/episodes/${episodeId}`)
  },

  async generateEpisodeScript(episodeId: number) {
    return api.post(`/episodes/${episodeId}/generate-script`)
  },

  async runEpisodePipeline(episodeId: number) {
    return api.post(`/episodes/${episodeId}/pipeline`)
  }
}