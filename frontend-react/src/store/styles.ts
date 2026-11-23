/**
 * 风格预设缓存（对应 Vue 版 stores/styles.js）。
 *
 * source 语义必须保留：'remote' 表示后端数据可信（含"全部停用"的合法空列表），
 * 'fallback' 仅在后端请求失败时生效。混用会导致用户把风格全停用后
 * 前端仍回退到内置 6 种，与「风格预设」管理页不一致。
 */
import { create } from 'zustand'

import api, { unwrap } from '@/api/client'
import { asList } from '@/lib/format'
import { STYLES } from '@/lib/entities'

export interface StylePreset {
  id?: number
  name: string
  description?: string
  prompt?: string
  negative_prompt?: string
  is_active?: boolean
  sort_order?: number
  color?: string
}

function fallbackPresets(): StylePreset[] {
  return STYLES.map((name) => ({ name, description: '' }))
}

interface StylesState {
  presets: StylePreset[]
  loaded: boolean
  loading: boolean
  source: 'remote' | 'fallback'
  /** force=true 时忽略缓存（管理页变更后调用以即时同步） */
  fetch: (force?: boolean) => Promise<void>
}

export const useStylesStore = create<StylesState>()((set, get) => ({
  presets: [],
  loaded: false,
  loading: false,
  source: 'remote',

  async fetch(force = false) {
    const { loading, loaded } = get()
    if (loading) return
    if (loaded && !force) return
    set({ loading: true })
    try {
      const data = unwrap<unknown>(
        await api.get('/styles', { params: { page: 1, page_size: 100, include_inactive: false } })
      )
      const list = asList<StylePreset>(data, 'items', 'styles', 'list')
      set({
        presets: list.filter((p) => p.is_active !== false),
        source: 'remote',
        loaded: true
      })
    } catch {
      /* 仅请求失败时回退内置常量；空列表是合法状态，不回退 */
      set({ presets: fallbackPresets(), source: 'fallback', loaded: true })
    } finally {
      set({ loading: false })
    }
  }
}))