import client from './client'

// 后端统一响应：解包后这里拿到的是 data 字段
interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface UserInfo {
  id: string
  username: string
  nickname: string | null
  email: string | null
  avatar: string | null
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export const authApi = {
  register(username: string, password: string) {
    return client.post<unknown, Wrapped<UserInfo>>('/auth/register', {
      username,
      password,
    })
  },
  login(username: string, password: string) {
    return client.post<unknown, Wrapped<TokenPair>>('/auth/login', {
      username,
      password,
    })
  },
  me() {
    return client.get<unknown, Wrapped<UserInfo>>('/auth/me')
  },
  logout() {
    return client.post<unknown, Wrapped<null>>('/auth/logout')
  },
  changePassword(oldPassword: string, newPassword: string) {
    return client.put<unknown, Wrapped<null>>('/auth/password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
  updateProfile(nickname: string) {
    return client.put<unknown, Wrapped<UserInfo>>('/auth/profile', { nickname })
  },
  uploadAvatar(file: File) {
    const form = new FormData()
    form.append('file', file)
    return client.post<unknown, Wrapped<UserInfo>>('/auth/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
