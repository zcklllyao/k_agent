import { create } from 'zustand'

// 聊天页把「会话历史 / 新对话 / 分享」操作回调注册到这里，
// 供 MainLayout 顶栏在手机端聊天页渲染（替代搜索框），合并成一行。
interface ChatHeaderState {
  active: boolean // 当前是否在聊天页（已注册操作）
  openHistory?: () => void // 打开会话历史抽屉
  newChat?: () => void // 新建对话
  openShare?: () => void // 打开分享弹窗
  canShare: boolean // 当前会话是否可分享（有消息）
  register: (actions: {
    openHistory: () => void
    newChat: () => void
    openShare: () => void
  }) => void
  setCanShare: (v: boolean) => void
  clear: () => void
}

export const useChatHeaderStore = create<ChatHeaderState>((set) => ({
  active: false,
  canShare: false,
  register: ({ openHistory, newChat, openShare }) =>
    set({ active: true, openHistory, newChat, openShare }),
  setCanShare: (v) => set({ canShare: v }),
  clear: () =>
    set({
      active: false,
      openHistory: undefined,
      newChat: undefined,
      openShare: undefined,
      canShare: false,
    }),
}))
