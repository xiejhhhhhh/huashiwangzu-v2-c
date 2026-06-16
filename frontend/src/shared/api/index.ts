import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { 统一响应 } from './types'
import { 获取错误信息 } from './response-transform'

const TOKEN_KEY = 'v2_auth_token'

export const API_BASE_URL = '/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 从 localStorage 恢复 Token，启动时设置默认头 + 每次请求自动带上
const savedToken = localStorage.getItem(TOKEN_KEY)
if (savedToken) {
  api.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let 正在跳转登录页 = false
const 已重试请求 = new Set<string>()
const 错误节流 = new Map<string, number>()
const 节流间隔 = 30000

function 上报前端错误(url: string, 状态码: number | undefined, 错误信息: string) {
  if (url.includes('/logs/frontend-error')) return
  void axios.post(`${API_BASE_URL}/logs/frontend-error`, {
    url, status_code: 状态码 || 0, error_message: 错误信息, page_path: window.location.pathname,
  }, { withCredentials: true, timeout: 3000 }).catch(() => undefined)
}

function 节流记录错误(url: string, 状态码: number | undefined, 错误信息: string) {
  const key = `${url}|${状态码}`
  const 上次 = 错误节流.get(key) || 0
  const 现在 = Date.now()
  if (现在 - 上次 > 节流间隔) {
    错误节流.set(key, 现在)
    console.error(`[API] ${状态码 || '网络异常'} ${url} — ${错误信息}`)
    上报前端错误(url, 状态码, 错误信息)
  }
}

api.interceptors.response.use(
  (response) => {
    let 数据 = response.data
    // 登录响应: V2 返回 {success, data: {access_token, user}, error}
    // 需要把 user 提到顶层，token 也合并进去
    if (数据?.data?.access_token) {
      const 载荷 = 数据.data
      // 保存 Token 到 localStorage（页面刷新后恢复）并立即设置默认头
      localStorage.setItem(TOKEN_KEY, 载荷.access_token)
      api.defaults.headers.common['Authorization'] = `Bearer ${载荷.access_token}`
      return {
        success: true,
        data: { user: 载荷.user || null, access_token: 载荷.access_token, token_type: 载荷.token_type },
        error: null,
      }
    }
    // 普通响应: 透传原始数据，不做中文化转换
    return 数据
  },
  async (error) => {
    const 状态码 = error.response?.status
    const 请求URL = error.config?.url
    const 是登录请求 = 请求URL?.endsWith('/login') === true
    const 当前路径 = window.location.pathname
    const 已在登录页 = 当前路径 === '/' || 当前路径 === '/login'

    if (状态码 === 401 && !是登录请求 && !已在登录页) {
      if (!已重试请求.has(请求URL)) {
        已重试请求.add(请求URL)
        await new Promise(r => setTimeout(r, 500))
        try {
          const res = await api.request(error.config)
          return res
        } catch {
          已重试请求.delete(请求URL)
          if (!正在跳转登录页) {
            正在跳转登录页 = true
            window.location.replace('/')
            window.setTimeout(() => { 正在跳转登录页 = false }, 1000)
          }
          return Promise.reject(获取错误信息(error))
        }
      }
      if (!正在跳转登录页) {
        正在跳转登录页 = true
        window.location.replace('/')
        window.setTimeout(() => { 正在跳转登录页 = false }, 1000)
      }
    }
    if (状态码 === 403) ElMessage.error('你没有权限操作这个内容')
    const 错误详情 = 获取错误信息(error)
    节流记录错误(请求URL || '未知', 状态码, 错误详情.error || '未知错误')
    return Promise.reject(错误详情)
  }
)

export default api
export type { 统一响应, 接口响应 } from './types'
