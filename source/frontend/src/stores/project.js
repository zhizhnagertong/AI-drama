import { defineStore } from 'pinia'

/** 当前项目缓存：进入 Editor / 详情页时写入，离开时保留供返回快速渲染 */
export const useProjectStore = defineStore('project', {
  state: () => ({
    current: null,
    storyboards: [],
    characters: [],
    assets: [],
    timelines: []
  }),
  actions: {
    setProject(detail) {
      this.current = detail
    },
    setAll({ project, storyboards, characters, assets, timelines } = {}) {
      if (project !== undefined) this.current = project
      if (storyboards !== undefined) this.storyboards = storyboards
      if (characters !== undefined) this.characters = characters
      if (assets !== undefined) this.assets = assets
      if (timelines !== undefined) this.timelines = timelines
    },
    clear() {
      this.current = null
      this.storyboards = []
      this.characters = []
      this.assets = []
      this.timelines = []
    }
  }
})
