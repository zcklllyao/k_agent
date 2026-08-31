import { create } from 'zustand'
import { skillApi, type Skill } from '@/api/skills'

interface SkillState {
  list: Skill[]
  loaded: boolean
  loading: boolean
  refresh: () => Promise<void>
  ensureLoaded: () => Promise<void>
}

export const useSkillStore = create<SkillState>((set, get) => ({
  list: [],
  loaded: false,
  loading: false,
  refresh: async () => {
    set({ loading: true })
    try {
      const { data } = await skillApi.list()
      set({ list: data, loaded: true })
    } finally {
      set({ loading: false })
    }
  },
  ensureLoaded: async () => {
    if (get().loaded || get().loading) return
    await get().refresh()
  },
}))
