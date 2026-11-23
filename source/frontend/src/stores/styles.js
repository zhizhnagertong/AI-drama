import { defineStore } from 'pinia'
import api, { unwrap } from '../api'
import { STYLES, asList } from '../utils'

/** 后端不可用时的兜底：用内置 STYLES 常量构造只读预设 */
function fallbackPresets() {
  return STYLES.map((name) => ({ name, description: '' }))
}

export const useStyleStore = defineStore('styles', {
  state: () => ({
    presets: [],
    loaded: false,
    loading: false,
    /** 'remote' = 后端数据可信（含合法的"空列表"）；'fallback' = 请求失败回退内置 */
    source: 'remote'
  }),
  getters: {
    names: (s) => s.presets.map((p) => p.name),
    descOf: (s) => (name) => s.presets.find((p) => p.name === name)?.description || '',
    /** 后端可达但启用风格为 0（用户全部停用） */
    emptyRemote: (s) => s.loaded && s.source === 'remote' && s.presets.length === 0
  },
  actions: {
    /** 拉取启用中的风格预设（force=true 时忽略缓存，管理页变更后调用以即时同步） */
    async fetch(force = false) {
      if (this.loading) return
      if (this.loaded && !force) return
      this.loading = true
      try {
        const data = unwrap(
          await api.get('/styles', { params: { page: 1, page_size: 100, include_inactive: false } })
        )
        const list = asList(data, 'items', 'styles', 'list')
        this.presets = list.filter((p) => p.is_active !== false)
        this.source = 'remote'
        this.loaded = true
      } catch {
        /* 仅请求失败时回退到内置常量；空列表是合法状态不回退 */
        this.presets = fallbackPresets()
        this.source = 'fallback'
        this.loaded = true
      } finally {
        this.loading = false
      }
    }
  }
})
