/** 展示层格式化工具（自 Vue 版 utils/index.js 中抽出的最小子集）。 */

import type { Project, User } from '@/types'

/* ---------------- 渐变占位 ---------------- */

export function gradVar(id: number | undefined): string {
  const idx = ((((Number(id) || 0) % 8) + 8) % 8) + 1
  return `var(--grad-${idx})`
}

export function firstChar(text?: string): string {
  const t = String(text || '').trim()
  return t ? t[0].toUpperCase() : '剧'
}

export function displayNameOf(user: User | null): string {
  return user?.nickname || user?.username || user?.name || '创作者'
}

/* ---------------- 时间 ---------------- */

export function fmtTime(v?: string): string {
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

/* ---------------- 数据取值容错 ---------------- */

/** 兼容裸数组 / {projects:[]} / {list:[]} / {items:[]} 三种返回结构 */
export function asList<T>(x: unknown, ...keys: string[]): T[] {
  if (Array.isArray(x)) return x as T[]
  if (!x || typeof x !== 'object') return []
  const obj = x as Record<string, unknown>
  for (const k of keys) {
    if (Array.isArray(obj[k])) return obj[k] as T[]
  }
  if (Array.isArray(obj.items)) return obj.items as T[]
  return []
}

export function imgUrlOf(o?: Partial<Project> | string | null): string {
  if (!o) return ''
  if (typeof o === 'string') return o
  return (
    o.cover_url ||
    (o as Record<string, unknown>).image_url as string ||
    ''
  )
}

export const PROJECT_STATUS: Record<string, { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'neutral' },
  script_ready: { label: '剧本就绪', tone: 'primary' },
  producing: { label: '制作中', tone: 'warning' },
  completed: { label: '已完成', tone: 'success' },
  failed: { label: '失败', tone: 'danger' }
}

export function statusText(s?: string): string {
  return (s && PROJECT_STATUS[s]?.label) || s || ''
}

/** 状态点语义：进行中=success、已完成=primary、失败=error */
export function dotClassOf(s?: string): string {
  if (s === 'completed') return 'done'
  if (s === 'producing' || s === 'script_ready') return 'on'
  if (s === 'failed') return 'err'
  return ''
}