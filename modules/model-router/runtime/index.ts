/**
 * 模型路由模块运行时 —— 精简版
 *
 * 只负责与框架的 API 调用封装（GET/POST/PUT/DELETE + 鉴权头 + 401 处理），
 * 不依赖框架其它基础设施（文件/办公/任务等命名空间）。
 *
 * 用法：
 *   import { apiGet, apiPost, apiPut, apiDelete } from '../runtime'
 */

export interface RuntimeConfig {
  mode: 'sandbox' | 'framework'
  api_base_url: string
  permissions: string[]
  module_settings: Record<string, unknown>
}

interface ApiEnvelope<T> {
  success: boolean
  data: T
  error: string | null
}

let _config: RuntimeConfig | null = null
const TOKEN_KEY = 'v2_auth_token'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isEnvelope<T>(value: unknown): value is ApiEnvelope<T> {
  return isRecord(value) && typeof value.success === 'boolean' && 'data' in value
}

async function loadSandboxConfig(): Promise<RuntimeConfig> {
  try {
    const res = await fetch('/runtime.config.json')
    if (res.ok) return await res.json()
  } catch { /* 忽略，走默认配置 */ }
  return { mode: 'sandbox', api_base_url: '/api', permissions: ['viewer'], module_settings: {} }
}

/** 初始化运行时配置（沙盒模式读 runtime.config.json，框架模式读全局注入变量） */
export async function initRuntime(_moduleKey = 'model-router'): Promise<RuntimeConfig> {
  if (_config) return _config
  const isSandbox = !!document.querySelector('.sandbox-badge')
  if (isSandbox) {
    _config = await loadSandboxConfig()
  } else {
    const injected = (window as unknown as { __HUASHI_RUNTIME__?: RuntimeConfig }).__HUASHI_RUNTIME__
    _config = injected
      ? { ...injected, mode: 'framework' }
      : { mode: 'framework', api_base_url: '/api', permissions: ['viewer'], module_settings: {} }
  }
  return _config
}

export function getApiUrl(path: string): string {
  const base = _config?.api_base_url ?? '/api'
  return `${base}${path}`
}

export function authHeaders(): HeadersInit {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

let __redirecting = false

function handle401(status: number): boolean {
  if (status !== 401) return false
  if (_config?.mode === 'framework') return true
  localStorage.removeItem(TOKEN_KEY)
  if (!__redirecting) {
    __redirecting = true
    window.location.replace('/')
  }
  return true
}

async function unwrap<T>(resp: Response, path: string): Promise<T> {
  if (handle401(resp.status)) throw new Error('登录已失效，请重新登录')
  const payload: unknown = await resp.json().catch(() => null)
  if (!resp.ok) {
    const message = isEnvelope<unknown>(payload) && payload.error ? payload.error : `请求 ${path} 失败 (HTTP ${resp.status})`
    throw new Error(String(message))
  }
  if (isEnvelope<T>(payload)) {
    if (!payload.success) throw new Error(payload.error || '请求失败')
    return payload.data
  }
  return payload as T
}

export async function apiGet<T>(path: string): Promise<T> {
  await initRuntime()
  const r = await fetch(getApiUrl(path), { headers: authHeaders() })
  return unwrap<T>(r, path)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  await initRuntime()
  const r = await fetch(getApiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return unwrap<T>(r, path)
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  await initRuntime()
  const r = await fetch(getApiUrl(path), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return unwrap<T>(r, path)
}

export async function apiDelete<T>(path: string): Promise<T> {
  await initRuntime()
  const r = await fetch(getApiUrl(path), { method: 'DELETE', headers: authHeaders() })
  return unwrap<T>(r, path)
}

/** 跨模块调用桥（与其它精简运行时保持一致的最小 platform 命名空间） */
export const platform = {
  modules: {
    async call<T = unknown>(targetModule: string, action: string, parameters: Record<string, unknown> = {}): Promise<T> {
      return apiPost<T>('/modules/call', {
        target_module: targetModule,
        action,
        parameters,
      })
    },
  },
}
