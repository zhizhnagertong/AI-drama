import { defineStore } from 'pinia'

const KEY = 'theme'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
  }),
  getters: {
    isDark: (s) => s.theme === 'dark'
  },
  actions: {
    setTheme(t) {
      this.theme = t === 'light' ? 'light' : 'dark'
      localStorage.setItem(KEY, this.theme)
      this.apply()
    },
    toggle() {
      this.setTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
    apply() {
      const el = document.documentElement
      el.dataset.theme = this.theme
      el.classList.toggle('dark', this.theme === 'dark')
    }
  }
})
