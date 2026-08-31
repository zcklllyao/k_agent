import { create } from 'zustand'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'

interface KnowledgeBaseState {
  list: KnowledgeBase[]
  loaded: boolean
  loading: boolean
  refresh: () => Promise<void>
  ensureLoaded: () => Promise<void>
  defaultKb: () => KnowledgeBase | undefined
}

export const useKnowledgeBaseStore = create<KnowledgeBaseState>((set, get) => ({
  list: [],
  loaded: false,
  loading: false,
  refresh: async () => {
    set({ loading: true })
    try {
      const { data } = await knowledgeBaseApi.list()
      set({ list: data, loaded: true })
    } finally {
      set({ loading: false })
    }
  },
  ensureLoaded: async () => {
    if (get().loaded || get().loading) return
    await get().refresh()
  },
  defaultKb: () => get().list.find((k) => k.is_default),
}))
