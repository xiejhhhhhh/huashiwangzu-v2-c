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

declare global {
  interface Window {
    __MODULE_RUNTIME_CONFIG__?: RuntimeConfig
  }
}

let runtimeConfig: RuntimeConfig | null = null
const TOKEN_KEY = 'v2_auth_token'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isEnvelope<T>(value: unknown): value is ApiEnvelope<T> {
  return isRecord(value) && typeof value.success === 'boolean' && 'data' in value && 'error' in value
}

export async function initRuntime(): Promise<RuntimeConfig> {
  if (runtimeConfig) return runtimeConfig
  if (window.__MODULE_RUNTIME_CONFIG__) {
    runtimeConfig = window.__MODULE_RUNTIME_CONFIG__
    return runtimeConfig
  }
  try {
    const response = await fetch('/runtime.config.json')
    if (response.ok) {
      runtimeConfig = (await response.json()) as RuntimeConfig
      return runtimeConfig
    }
  } catch {
    // Framework mode injects config; sandbox falls back below when config is absent.
  }
  runtimeConfig = {
    mode: 'framework',
    api_base_url: '/api',
    permissions: ['viewer'],
    module_settings: {},
  }
  return runtimeConfig
}

function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const cfg = await initRuntime()
  const normalizedBase = cfg.api_base_url.replace(/\/$/, '')
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const response = await fetch(`${normalizedBase}${normalizedPath}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: JSON.stringify(body),
  })
  const payload: unknown = await response.json()
  if (!response.ok) {
    const message = isEnvelope<unknown>(payload) && payload.error ? payload.error : `HTTP ${response.status}`
    throw new Error(message)
  }
  if (!isEnvelope<T>(payload)) {
    throw new Error('Unexpected API response shape')
  }
  if (!payload.success) {
    throw new Error(payload.error || 'Request failed')
  }
  return payload.data
}

export const platform = {
  modules: {
    async call<T = unknown>(targetModule: string, action: string, parameters: Record<string, unknown>): Promise<T> {
      return apiPost<T>('/modules/call', {
        target_module: targetModule,
        action,
        parameters,
      })
    },
  },
}
