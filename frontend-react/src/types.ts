/** 后端实体类型（覆盖编辑器涉及的分镜/镜头/版本/素材/时间线）。 */

export interface User {
  id?: number
  username?: string
  nickname?: string
  name?: string
  email?: string
  avatar?: string
}

export interface LoginResult {
  access_token: string
  refresh_token?: string
  expires_in?: number
  refresh_expires_in?: number
  user?: User
}

export interface Project {
  id: number
  title?: string
  genre?: string
  style?: string
  style_name?: string
  status?: string
  cover_url?: string
  aspect_ratio?: string
  inspiration?: string
  created_at?: string
  updated_at?: string
  characters?: unknown[]
  episodes?: unknown[]
  character_count?: number
  episode_count?: number
  stats?: { character_count?: number; storyboard_count?: number }
  [key: string]: unknown
}

export interface ShotVersion {
  id?: number
  version_no?: number
  image_url?: string
  video_url?: string | null
  prompt?: string
  seed?: number | null
  is_selected?: boolean
  selected?: boolean
  status?: string
  [key: string]: unknown
}

export interface Shot {
  id?: number
  shot_id?: number
  storyboard_id?: number
  selected_version_id?: number | null
  video_url?: string | null
  status?: string
  versions?: ShotVersion[]
  [key: string]: unknown
}

/** 分镜：字段做了多别名归一（后端历史字段不统一），因此保留索引签名 */
export interface Storyboard {
  id?: number
  episode_id?: number | null
  order_index?: number
  shot_type?: string
  description?: string
  dialogue?: string
  emotion?: string
  duration?: number
  character_name?: string
  image_url?: string
  video_url?: string
  shots?: Shot[]
  [key: string]: unknown
}

export interface Asset {
  id?: number
  project_id?: number
  type?: string
  url?: string
  meta?: Record<string, unknown>
  storyboard_id?: number
  [key: string]: unknown
}

export interface Character {
  id?: number
  project_id?: number
  name?: string
  description?: string
  prompt_template?: string
  ref_image_url?: string
  voice?: string
  voice_speed?: number | null
  [key: string]: unknown
}

export interface Episode {
  id: number
  project_id?: number
  episode_number?: number
  title?: string
  status?: string
  synopsis?: string
  [key: string]: unknown
}

export interface TimelineItem {
  id: number | string
  storyboard_id?: number
  shot_id?: number
  version_id?: number
  media_url: string
  duration: number
  subtitle: string
  audio_url: string
}

export interface Timeline {
  id: number
  project_id?: number
  episode_id?: number | null
  status?: string
  output_url?: string | null
  items?: TimelineItem[]
  [key: string]: unknown
}

/* ---------------- 任务 / 流水线 ---------------- */

export type TaskStatus = 'pending' | 'queued' | 'running' | 'processing' | 'succeeded' | 'failed' | 'canceled'

export interface TaskInfo {
  task_id: number | string
  type?: string
  status?: TaskStatus | string
  progress?: number
  error?: string | null
  [key: string]: unknown
}

export interface PipelineStep {
  status?: 'pending' | 'running' | 'partial' | 'done' | string
  completed?: number
  total?: number
}

export type PipelineSteps = Record<string, PipelineStep | undefined>

export interface ProjectDetailResponse {
  project?: Project
  episodes?: Episode[]
  storyboards?: Storyboard[]
  characters?: Character[]
  assets?: Asset[]
  timelines?: Timeline[]
  [key: string]: unknown
}

/** 后端统一错误体：{code, biz_code, message, field_errors} */
export interface ApiErrorBody {
  code?: number
  biz_code?: string
  message?: string
  detail?: string
  field_errors?: Record<string, string>
}