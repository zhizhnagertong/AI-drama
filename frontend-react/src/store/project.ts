/**
 * 当前项目缓存（对应 Vue 版 stores/project.js）。
 * 进入 Editor / 详情页时写入，离开时保留，供返回时快速渲染。
 */
import { create } from 'zustand'

import type { Asset, Character, Project, Storyboard, Timeline } from '@/types'

interface ProjectState {
  current: Project | null
  storyboards: Storyboard[]
  characters: Character[]
  assets: Asset[]
  timelines: Timeline[]
  setProject: (detail: Project | null) => void
  setAll: (payload: {
    project?: Project | null
    storyboards?: Storyboard[]
    characters?: Character[]
    assets?: Asset[]
    timelines?: Timeline[]
  }) => void
  clear: () => void
}

export const useProjectStore = create<ProjectState>()((set) => ({
  current: null,
  storyboards: [],
  characters: [],
  assets: [],
  timelines: [],

  setProject(detail) {
    set({ current: detail })
  },

  setAll({ project, storyboards, characters, assets, timelines }) {
    set((state) => ({
      current: project !== undefined ? project : state.current,
      storyboards: storyboards !== undefined ? storyboards : state.storyboards,
      characters: characters !== undefined ? characters : state.characters,
      assets: assets !== undefined ? assets : state.assets,
      timelines: timelines !== undefined ? timelines : state.timelines
    }))
  },

  clear() {
    set({ current: null, storyboards: [], characters: [], assets: [], timelines: [] })
  }
}))