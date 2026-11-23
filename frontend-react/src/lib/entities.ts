/**
 * 实体归一化工具（移植自 Vue 版 utils/index.js）。
 *
 * 这一层刻意使用宽松类型：它的存在前提就是「后端返回结构历史上不统一」
 * （分镜字段有 shot_type/scene/description 多种别名），
 * 强类型在这里只会逼出一堆无意义的断言，真正的类型收敛应发生在后端。
 */
import type { Asset, Shot, ShotVersion, Storyboard, Timeline, TimelineItem } from '@/types'

// 展示层工具在 format.ts，这里按实体语义再导出一次，便于组件只从一个模块取
export { gradVar as gradVarOf, firstChar as firstCharOf } from '@/lib/format'

type Lo = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

/* ---------------- 素材 ---------------- */

export function assetUrlOf(a?: Lo | null): string {
  if (!a) return ''
  return a.url || a.file_url || a.audio_url || a.video_url || a.image_url || ''
}

export function assetTypeOf(a?: Lo | null): string {
  if (!a) return ''
  if (a.type) return a.type as string
  if (a.asset_type) return a.asset_type as string
  const url = assetUrlOf(a)
  if (/\.(mp4|webm|mov)(\?|$)/i.test(url)) return 'video'
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return 'audio'
  if (/\.(png|jpe?g|webp|gif)(\?|$)/i.test(url)) return 'image'
  return 'file'
}

export function assetNameOf(a?: Lo | null): string {
  if (!a) return ''
  return a.name || a.filename || a.title || assetUrlOf(a).split('/').pop() || '未命名素材'
}

/** 音频素材：按 storyboard_id 匹配（meta 或顶层字段），取最新一条（assets 按 id desc） */
export function audioOfSb(assets: Asset[] | undefined, sbId?: number): string {
  const list = (assets || []).filter((a) => {
    if (assetTypeOf(a as Lo) !== 'audio') return false
    const meta = (a.meta || {}) as Lo
    return meta.storyboard_id == sbId || a.storyboard_id == sbId
  })
  return list.length ? assetUrlOf(list[0] as Lo) : ''
}

/* ---------------- 分镜 ---------------- */

export function normStoryboard(sb?: Lo | null, i = 0): Storyboard {
  if (!sb || typeof sb !== 'object') return { shots: [] }
  return {
    ...sb,
    order_index: sb.order_index ?? i,
    shot_type: sb.shot_type ?? sb.shot_size ?? sb.scale ?? '',
    description: sb.description ?? sb.scene ?? sb.visual_description ?? sb.scene_description ?? '',
    dialogue: sb.dialogue ?? sb.line ?? sb.lines ?? '',
    emotion: sb.emotion ?? sb.mood ?? '',
    duration: sb.duration ?? sb.duration_sec ?? sb.duration_seconds ?? 3,
    character_name: sb.character_name ?? sb.character ?? '',
    shots: Array.isArray(sb.shots) ? sb.shots : []
  } as Storyboard
}

/** 展开分镜下所有镜头版本，附带 shot_id */
export function versionsOf(sb?: Storyboard | null): Array<ShotVersion & { shot_id?: number }> {
  const out: Array<ShotVersion & { shot_id?: number }> = []
  for (const sh of (sb?.shots || []) as Shot[]) {
    for (const v of sh.versions || []) {
      out.push({ ...v, shot_id: (sh.id ?? sh.shot_id) as number })
    }
  }
  return out
}

/** 已选定版本（跨镜头取第一个） */
export function selectedOf(sb?: Storyboard | null): (ShotVersion & { shot_id?: number }) | null {
  for (const sh of (sb?.shots || []) as Shot[]) {
    const versions = sh.versions || []
    const sel =
      versions.find((v) => v.id === sh.selected_version_id || v.id === (sh as Lo).selected_version) ||
      versions.find((v) => v.is_selected || v.selected)
    if (sel) return { ...sel, shot_id: (sh.id ?? sh.shot_id) as number }
  }
  return null
}

export function hasSelected(sb?: Storyboard | null): boolean {
  return ((sb?.shots || []) as Shot[]).some((sh) => {
    const versions = sh.versions || []
    return (
      versions.some((v) => v.id === sh.selected_version_id) ||
      versions.some((v) => v.is_selected || v.selected) ||
      !!sh.selected_version_id
    )
  })
}

/** 分镜缩略图：优先选定版本，否则最新版本，否则分镜自带图 */
export function thumbOf(sb?: Storyboard | null): string {
  const sel = selectedOf(sb)
  if (sel) return imgOf(sel)
  const versions = versionsOf(sb)
  if (versions.length) return imgOf(versions[versions.length - 1])
  return imgOf(sb as Lo)
}

export function videoUrlOf(sb?: Storyboard | null): string {
  for (const sh of (sb?.shots || []) as Shot[]) {
    const versions = sh.versions || []
    const sel =
      versions.find((v) => v.id === sh.selected_version_id) ||
      versions.find((v) => v.is_selected || v.selected)
    if (sel?.video_url) return sel.video_url
    if (sh.video_url) return sh.video_url
    const withVideo = versions.find((v) => v.video_url)
    if (withVideo?.video_url) return withVideo.video_url
  }
  return (sb?.video_url as string) || ''
}

/** 多字段候选的图片地址（与原版 imgUrlOf 等价） */
export function imgOf(o?: Lo | null): string {
  if (!o) return ''
  if (typeof o === 'string') return o
  return (
    o.image_url ||
    o.ref_image_url ||
    o.url ||
    o.file_url ||
    o.thumbnail_url ||
    o.preview_url ||
    o.cover_url ||
    ''
  )
}

/* ---------------- 时间线 ---------------- */

export function normTimeline(t?: Lo | null): Timeline {
  if (!t || typeof t !== 'object') return { id: 0, items: [] }
  const raw = Array.isArray(t.items) ? t.items : (t.items?.items ?? t.timeline_items ?? [])
  const items: TimelineItem[] = (raw as Lo[]).map((it, i) => ({
    id: it.id ?? it.shot_id ?? i,
    storyboard_id: it.storyboard_id,
    shot_id: it.shot_id ?? it.id,
    version_id: it.version_id,
    media_url: it.media_url || imgOf(it) || imgOf(it.shot || {}),
    duration: it.duration_sec ?? it.duration ?? it.duration_seconds ?? 3,
    subtitle: it.subtitle ?? it.subtitle_text ?? it.dialogue ?? '',
    audio_url: it.audio_url || it.voice_url || ''
  }))
  return { ...t, items } as Timeline
}

/* ---------------- 文案 ---------------- */

export function taskTypeLabel(t?: string): string {
  const key = String(t || '').toLowerCase()
  if (key.includes('pipeline')) return 'AI 流水线'
  if (key.includes('script')) return '剧本生成'
  if (key.includes('ref')) return '角色参考图'
  if (key.includes('cover')) return '封面生成'
  if (key.includes('image')) return '画面生成'
  if (key.includes('video')) return '视频生成'
  if (key.includes('voice') || key.includes('tts') || key.includes('audio')) return '配音合成'
  if (key.includes('composite')) return '成片合成'
  if (key.includes('timeline')) return '时间线生成'
  return t || '生成任务'
}

export const TASK_STATUS: Record<string, { label: string; tag: string }> = {
  pending: { label: '排队中', tag: 'info' },
  running: { label: '生成中', tag: 'primary' },
  processing: { label: '生成中', tag: 'primary' },
  succeeded: { label: '已完成', tag: 'success' },
  failed: { label: '失败', tag: 'danger' },
  canceled: { label: '已取消', tag: 'info' }
}

export function taskStatusText(s?: string): string {
  return (s && TASK_STATUS[s]?.label) || s || ''
}

export function taskStatusTag(s?: string): string {
  return (s && TASK_STATUS[s]?.tag) || 'info'
}

export const VOICES = [
  { value: 'longxiaochun', label: '龙小淳（女声·温柔）' },
  { value: 'longcheng', label: '龙城（男声·浑厚）' },
  { value: 'longhua', label: '龙华（男声·磁性）' },
  { value: 'longshu', label: '龙书（女声·知性）' }
]

export function voiceLabel(v?: string): string {
  return VOICES.find((x) => x.value === v)?.label ?? v ?? '未设置'
}

export const SHOT_TYPES = ['远景', '全景', '中景', '近景', '特写']

/* ---------------- 创作页字典 ---------------- */

export const GENRES = ['科幻', '悬疑', '爱情', '武侠', '都市', '奇幻', '其他']

export const STYLES = ['赛博朋克', '水墨国风', '日系动漫', '美式漫画', '3D卡通', '写实']

export const RATIOS = [
  { value: '9:16', label: '9:16 竖屏' },
  { value: '16:9', label: '16:9 横屏' }
]

/** 已选定画面的镜头（用于「生成视频」目标判定） */
export function selectedShots(sb?: Storyboard | null): Shot[] {
  return ((sb?.shots || []) as Shot[]).filter((sh) => {
    const vs = sh.versions || []
    return (
      !!sh.selected_version_id ||
      vs.some((v) => v.id === sh.selected_version_id || v.is_selected || v.selected)
    )
  })
}

export function fmtDuration(s?: number | string): string {
  const n = Number(s)
  if (!Number.isFinite(n) || n <= 0) return ''
  return `${Math.round(n * 10) / 10}s`
}