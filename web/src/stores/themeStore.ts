import { create } from 'zustand'

export type ThemeMode = 'paper'

interface ThemeState {
  mode: ThemeMode
}

export const useThemeStore = create<ThemeState>(() => ({
  mode: 'paper',
}))
