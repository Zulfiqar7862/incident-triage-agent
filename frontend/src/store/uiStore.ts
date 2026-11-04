import { create } from 'zustand'
import { getOperator, setOperator as persistOperator } from '@/lib/api'

export type Theme = 'light' | 'dark' | 'system'

type UiState = {
  operator: string
  theme: Theme
  sseDisconnected: boolean
  thinkingPhase: string | null
  setOperator: (name: string) => void
  setTheme: (t: Theme) => void
  setSseDisconnected: (v: boolean) => void
  setThinkingPhase: (p: string | null) => void
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  const dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  root.classList.toggle('dark', dark)
}

const savedTheme = ((): Theme => {
  try {
    const t = localStorage.getItem('theme') as Theme | null
    if (t === 'light' || t === 'dark' || t === 'system') return t
  } catch {
    /* */
  }
  return 'system'
})()

applyTheme(savedTheme)

export const useUiStore = create<UiState>((set) => ({
  operator: getOperator(),
  theme: savedTheme,
  sseDisconnected: false,
  thinkingPhase: null,
  setOperator: (name) => {
    persistOperator(name)
    set({ operator: name })
  },
  setTheme: (theme) => {
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* */
    }
    applyTheme(theme)
    set({ theme })
  },
  setSseDisconnected: (sseDisconnected) => set({ sseDisconnected }),
  setThinkingPhase: (thinkingPhase) => set({ thinkingPhase }),
}))
