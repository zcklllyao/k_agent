import { create } from 'zustand'
import { authApi, type UserInfo } from '@/api/auth'

interface AuthState {
  user: UserInfo | null
  loading: boolean
  // 是否已登录（看本地有没有 token）
  isAuthenticated: () => boolean
  // 登录：存 token + 拉用户信息
  login: (username: string, password: string) => Promise<void>
  // 注册
  register: (username: string, password: string) => Promise<void>
  // 拉取当前用户（应用启动 / 刷新页面时调用）
  fetchUser: () => Promise<void>
  // 登出：清 token + 清状态
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: false,

  isAuthenticated: () => !!localStorage.getItem('access_token'),

  login: async (username, password) => {
    const { data } = await authApi.login(username, password)
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    await get().fetchUser()
  },

  register: async (username, password) => {
    await authApi.register(username, password)
  },

  fetchUser: async () => {
    if (!localStorage.getItem('access_token')) {
      set({ user: null })
      return
    }
    set({ loading: true })
    try {
      const { data } = await authApi.me()
      set({ user: data })
    } catch {
      // 拉取用户失败（token 失效 / 后端重启期间请求被丢弃等）：
      // 清掉本地 token，让路由守卫回落到登录页，避免一直转圈
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      set({ user: null })
    } finally {
      set({ loading: false })
    }
  },

  logout: async () => {
    try {
      await authApi.logout()
    } catch {
      // 忽略登出接口错误，本地清理为准
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ user: null })
  },
}))
