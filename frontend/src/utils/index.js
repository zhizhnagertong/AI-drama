/* ---------------- 常量字典 ---------------- */

export const GENRES = ['科幻', '悬疑', '爱情', '武侠', '都市', '奇幻', '其他']

export const STYLES = ['赛博朋克', '水墨国风', '日系动漫', '美式漫画', '3D卡通', '写实']

export const RATIOS = [
  { value: '9:16', label: '9:16 竖屏' },
  { value: '16:9', label: '16:9 横屏' }
]

export const VOICES = [
  { value: 'longxiaochun', label: '龙小淳（女声·温柔）' },
  { value: 'longcheng', label: '龙城（男声·浑厚）' },
  { value: 'longhua', label: '龙华（男声·磁性）' },
  { value: 'longshu', label: '龙书（女声·知性）' }
]

export const SHOT_TYPES = ['远景', '全景', '中景', '近景', '特写']

export const PROJECT_STATUS = {
  draft: { label: '草稿', tag: 'info' },
  script_ready: { label: '剧本就绪', tag: 'primary' },
  producing: { label: '制作中', tag: 'warning' },
  completed: { label: '已完成', tag: 'success' },
  failed: { label: '失败', tag: 'danger' }
}

export const TASK_STATUS = {
  pending: { label: '排队中', tag: 'info' },
  running: { label: '生成中', tag: 'primary' },
  processing: { label: '生成中', tag: 'primary' },
  succeeded: { label: '已完成', tag: 'success' },
  failed: { label: '失败', tag: 'danger' },
  canceled: { label: '已取消', tag: 'info' }
}

export function statusText(s) {
  return PROJECT_STATUS[s]?.label ?? s ?? ''
}

export function statusTagType(s) {
  return PROJECT_STATUS[s]?.tag ?? 'info'
}

export function taskStatusText(s) {
  return TASK_STATUS[s]?.label ?? s ?? ''
}

export function taskStatusTag(s) {
  return TASK_STATUS[s]?.tag ?? 'info'
}

export function taskTypeLabel(t) {
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

export function voiceLabel(v) {
  return VOICES.find((x) => x.value === v)?.label ?? v ?? '未设置'
}

/* ---------------- 渐变占位 ---------------- */

export function gradVar(id) {
  const idx = (((Number(id) || 0) % 8) + 8) % 8 + 1
  return `var(--grad-${idx})`
}

export function firstChar(text) {
  const t = String(text || '').trim()
  return t ? t[0].toUpperCase() : '剧'
}

/* ---------------- 时间 ---------------- */

export function fmtTime(v) {
  if (!v) return ''
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return String(v)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

export function fmtDuration(s) {
  const n = Number(s)
  if (!Number.isFinite(n) || n <= 0) return ''
  return `${Math.round(n * 10) / 10}s`
}

/* ---------------- 数据取值容错 ---------------- */

export function asList(x, ...keys) {
  if (Array.isArray(x)) return x
  if (!x || typeof x !== 'object') return []
  for (const k of keys) {
    if (Array.isArray(x[k])) return x[k]
  }
  return x.items && Array.isArray(x.items) ? x.items : []
}

export function imgUrlOf(o) {
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

export function assetUrlOf(a) {
  if (!a) return ''
  return a.url || a.file_url || a.audio_url || a.video_url || a.image_url || ''
}

export function assetTypeOf(a) {
  if (!a) return ''
  if (a.type) return a.type
  if (a.asset_type) return a.asset_type
  const url = assetUrlOf(a)
  if (/\.(mp4|webm|mov)(\?|$)/i.test(url)) return 'video'
  if (/\.(mp3|wav|m4a|aac|ogg)(\?|$)/i.test(url)) return 'audio'
  if (/\.(png|jpe?g|webp|gif)(\?|$)/i.test(url)) return 'image'
  return 'file'
}

export function assetNameOf(a) {
  if (!a) return ''
  return a.name || a.filename || a.title || assetUrlOf(a).split('/').pop() || '未命名素材'
}

/* ---------------- 分镜数据归一化 ---------------- */

export function normStoryboard(sb, i = 0) {
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
  }
}

/** 展开分镜下所有镜头版本，附带 shot_id */
export function versionsOf(sb) {
  const out = []
  for (const sh of sb?.shots || []) {
    for (const v of sh.versions || []) {
      out.push({ ...v, shot_id: sh.id ?? sh.shot_id })
    }
  }
  return out
}

/** 已选定版本（跨镜头取第一个） */
export function selectedOf(sb) {
  for (const sh of sb?.shots || []) {
    const versions = sh.versions || []
    const sel =
      versions.find((v) => v.id === sh.selected_version_id || v.id === sh.selected_version) ||
      versions.find((v) => v.is_selected || v.selected)
    if (sel) return { ...sel, shot_id: sh.id ?? sh.shot_id }
  }
  return null
}

export function hasSelected(sb) {
  return (sb?.shots || []).some((sh) => {
    const versions = sh.versions || []
    return (
      versions.some((v) => v.id === sh.selected_version_id || v.id === sh.selected_version) ||
      versions.some((v) => v.is_selected || v.selected) ||
      !!sh.selected_version_id
    )
  })
}

/** 分镜缩略图：优先选定版本，否则最新版本，否则分镜自带图 */
export function thumbOf(sb) {
  const sel = selectedOf(sb)
  if (sel) return imgUrlOf(sel)
  const versions = versionsOf(sb)
  if (versions.length) return imgUrlOf(versions[versions.length - 1])
  return imgUrlOf(sb)
}

export function videoUrlOf(sb) {
  for (const sh of sb?.shots || []) {
    const versions = sh.versions || []
    const sel =
      versions.find((v) => v.id === sh.selected_version_id) ||
      versions.find((v) => v.is_selected || v.selected)
    if (sel?.video_url) return sel.video_url
    if (sh.video_url) return sh.video_url
    const withVideo = versions.find((v) => v.video_url)
    if (withVideo) return withVideo.video_url
  }
  return sb?.video_url || ''
}

/** 音频素材：按 storyboard_id 匹配（meta.storyboard_id 或顶层字段），取最新一条 */
export function audioOfSb(assets, sbId) {
  const list = (assets || []).filter((a) => {
    if (assetTypeOf(a) !== 'audio') return false
    const meta = a.meta || {}
    return meta.storyboard_id == sbId || a.storyboard_id == sbId
  })
  // assets 按 id desc 返回，list[0] 即最新配音
  return list.length ? assetUrlOf(list[0]) : ''
}
