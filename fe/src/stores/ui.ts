import { create } from 'zustand'

export type ThemePref = 'system' | 'light' | 'dark'

const KEY = 'gt:theme'

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    /* storage unavailable */
  }
  return 'system'
}

interface UiState {
  theme: ThemePref
  setTheme: (t: ThemePref) => void
}

export const useUi = create<UiState>((set) => ({
  theme: readPref(),
  setTheme: (theme) => {
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* ignore */
    }
    set({ theme })
  },
}))
