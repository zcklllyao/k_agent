import axios from 'axios'

// 统一请求封装：baseURL=/api，返回体 { code, message, data }
// timeout 给到 5 分钟：上传大文件 + 转存 OSS 在低带宽下耗时长，避免前端过早 timeout。
// 普通接口正常都是秒级返回，不受影响。
const client = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

// 请求拦截：附带 token（账号体系阶段启用）
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：解包 { code, message, data }
client.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body.code !== 'undefined' && body.code !== 0) {
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (error) => {
    // 401：token 失效/未登录，清除本地登录态并跳登录页
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    const message =
      error.response?.data?.message || error.message || '网络错误'
    return Promise.reject(new Error(message))
  },
)

export default client
