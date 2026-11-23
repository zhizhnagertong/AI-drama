import { create } from 'zustand'

export type Theme = 'dark' | 'light'

const KEY = 'theme'

function readTheme(): Theme {
  try {
    return window.localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

interface ThemeState {
  theme: Theme
  setTheme: (t: Theme) => void
  toggle: () => void
  apply: () => void
}

export const useThemeStore = create<ThemeState>()((set, get) => ({
  theme: readTheme(),

  setTheme(t) {
    const next: Theme = t === 'light' ? 'light' : 'dark'
    try {
      window.localStorage.setItem(KEY, next)
    } catch {
      /* ignore */
    }
    set({ theme: next })
    get().apply()
  },

  toggle() {
    get().setTheme(get().theme === 'dark' ? 'light' : 'dark')
  },

  apply() {
    const el = document.documentElement
    el.dataset.theme = get().theme
    el.classList.toggle('dark', get().theme === 'dark')
  }
}))