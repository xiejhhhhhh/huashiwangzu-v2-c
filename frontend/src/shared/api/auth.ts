import api from './index'
import type { 统一响应, 登录参数, 用户信息 } from './types'

export function 登录请求(参数: 登录参数) {
  return api.post<unknown, 统一响应<{ access_token: string; token_type: string; user: 用户信息 }>>('/login', 参数)
}

export function fetchCurrentUser请求() {
  return api.get<unknown, 统一响应<用户信息>>('/current-user')
}

export function 登出请求() {
  return api.post<unknown, 统一响应<null>>('/logout')
}
