/**
 * Office-gen module runtime SDK.
 * Provides platform namespace interface for the office-gen module.
 */

const TOKEN_KEY = 'v2_auth_token'

interface RuntimeConfig {
  api_base_url?: string
  mode?: 'sandbox' | 'framework'
}

let _config: RuntimeConfig = {
  api_base_url: '/api',
  mode: 'sandbox',
}

export function initRuntime(config: RuntimeConfig = {}): void {
  _config = { ...config, mode: 'framework' }
}

export function getApiUrl(path: string): string {
  const base = _config?.api_base_url ?? '/api'
  return `${base}${path}`
}

export function getMode(): 'sandbox' | 'framework' {
  return _config?.mode ?? 'sandbox'
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const url = getApiUrl(path)
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  if (!r.ok) throw new Error(`API ${path} returned ${r.status}`)
  const body = await r.json()
  if (!body.success) throw new Error(body.error ?? 'API error')
  return body.data as T
}

export const files = {
  async generateDocx(params: { filename: string; content: any[]; folder_id?: number }): Promise<any> {
    return apiPost<any>('/office-gen/docx', params)
  },
  async generateXlsx(params: { filename: string; sheets: any[]; folder_id?: number }): Promise<any> {
    return apiPost<any>('/office-gen/xlsx', params)
  },
  async generatePptx(params: { filename: string; slides: any[]; folder_id?: number }): Promise<any> {
    return apiPost<any>('/office-gen/pptx', params)
  },
  async generatePdf(params: { filename: string; content: any[]; folder_id?: number }): Promise<any> {
    return apiPost<any>('/office-gen/pdf', params)
  },
  async convert(params: { file_id: number; target_format?: string }): Promise<any> {
    return apiPost<any>('/office-gen/convert', params)
  },
}

export const platform = {
  files,
  auth: {
    token(): string | null {
      return localStorage.getItem(TOKEN_KEY)
    },
  },
  modules: {
    async call(targetModule: string, action: string, parameters: Record<string, unknown> = {}): Promise<unknown> {
      return apiPost<unknown>('/modules/call', { target_module: targetModule, action, parameters })
    },
    async capabilities(): Promise<string[]> {
      return apiPost<string[]>('/modules/capabilities')
    },
  },
}
