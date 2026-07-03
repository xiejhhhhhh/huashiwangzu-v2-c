/**
 * Module Runtime — terminal-tools
 *
 * Copied from modules/_template/runtime/index.ts.
 * All API paths, permissions, and settings are read through this layer.
 *
 * Usage:
 *   import { platform } from '../runtime'
 *   const files = await platform.files.list({ page: 1, page_size: 50 })
 */

// ── Type definitions ────────────────────────────────────────────────
export interface RuntimeConfig {
  mode: 'sandbox' | 'framework'
  api_base_url: string
  permissions: string[]
  module_settings: Record<string, unknown>
}

// ── Platform SDK types ──────────────────────────────────────────────

export interface CurrentUser {
  id: number
  username: string
  display_name: string
  role: string
  email: string | null
}

export interface FileListPage {
  items: FileItem[]
  total: number
  page: number
  page_size: number
}

export interface FileItem {
  id: number
  name: string
  extension: string | null
  size: number
  folder_id: number | null
  created_at: string
  is_folder: boolean
  storage_path: string | null
  mime_type: string | null
}

export interface FileDetail {
  id: number
  name: string
  extension: string
  size: number
  folder_id: number | null
  folder_name: string
  created_at: string
  updated_at: string
  storage_path: string
  deleted: boolean
  mime_type: string
}

export interface FileSearchPage {
  items: FileItem[]
  total: number
  page: number
  page_size: number
}

export interface UploadResult {
  exists: boolean
  id: number
  name: string
  extension: string
  size?: number
  mime_type?: string
  deduplicated?: boolean
}

export interface FileShareEntry {
  id: number
  file_id: number
  file_name: string
  extension: string
  shared_by_name: string
  shared_with_name?: string
  permission: 'read' | 'edit'
  created_at: string
}

export interface FileSharePage {
  items: FileShareEntry[]
  total: number
  page: number
  page_size: number
}

export interface FileAccessResult {
  accessible: boolean
  permission: 'owner' | 'read' | 'edit' | null
}

export interface FileOpenPayload {
  fileId: number
  fileName: string
  extension: string | null
  mimeType: string | null
  mode: 'view' | 'edit'
}

export interface OfficeStatus {
  package_id: number | null
  latest_version: number
  format_type: string
}

export interface OfficePackage {
  id: number
  file_id: number
  current_version_id: number | null
  format_type: string
  package_status: string
}

export interface OfficeVersion {
  id: number
  package_id: number
  version_number: number
  summary: string | null
  created_at: string
}

export interface ModelProfile {
  key: string
  name: string
  provider: string
  model: string
}

export interface ModelHealth {
  [providerName: string]: boolean
}

export interface ChatResult {
  content: string
  reasoning_content?: string
  tokens?: number
}

export interface EmbeddingResult {
  embeddings: number[][]
  count: number
}

export interface RerankResult {
  results: Array<{ index: number; score: number }>
}

export interface TaskInfo {
  id: number
  task_type: string
  status: string
  priority: number
  module: string
  error_message: string | null
  created_at: string | null
}

// ── Framework injection key ─────────────────────────────────────────
let _config: RuntimeConfig | null = null
const TOKEN_KEY = 'v2_auth_token'

// ── Sandbox config loader ───────────────────────────────────────────
async function loadSandboxConfig(): Promise<RuntimeConfig> {
  try {
    const res = await fetch('/runtime.config.json')
    if (res.ok) return await res.json()
  } catch { /* ignore */ }
  return {
    mode: 'sandbox',
    api_base_url: '/api',
    permissions: ['viewer'],
    module_settings: {},
  }
}

// ── Public API ──────────────────────────────────────────────────────

export async function initRuntime(_moduleKey: string): Promise<RuntimeConfig> {
  if (_config) return _config

  const isSandbox = !!(document.querySelector('.sandbox-badge'))
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

export function initFrameworkRuntime(config: RuntimeConfig): void {
  _config = { ...config, mode: 'framework' }
}

export function getApiUrl(path: string): string {
  const base = _config?.api_base_url ?? '/api'
  return `${base}${path}`
}

export function getMode(): 'sandbox' | 'framework' {
  return _config?.mode ?? 'sandbox'
}

export function hasPermission(permission: string): boolean {
  return _config?.permissions?.includes(permission) ?? false
}

export function getModuleSetting<T = unknown>(key: string, defaultValue?: T): T | undefined {
  return (_config?.module_settings?.[key] as T) ?? defaultValue
}

export function getRuntimeConfig(): Readonly<RuntimeConfig> {
  if (!_config) throw new Error('Runtime not initialized. Call initRuntime() first.')
  return _config
}

// ── Internal HTTP helper ────────────────────────────────────────────

let __redirecting = false

function _handle401(status: number): boolean {
  if (status !== 401) return false
  localStorage.removeItem(TOKEN_KEY)
  if (!__redirecting) {
    __redirecting = true
    window.location.replace('/')
  }
  return true
}

export function authHeaders(): HeadersInit {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiGet<T>(path: string): Promise<T> {
  const url = getApiUrl(path)
  const r = await fetch(url, { headers: authHeaders() })
  if (_handle401(r.status)) throw new Error('登录已失效，请重新登录')
  if (!r.ok) throw new Error(`API ${path} returned ${r.status}`)
  const body = await r.json()
  if (!body.success) throw new Error(body.error ?? 'API error')
  return body.data as T
}

async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const url = getApiUrl(path)
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  if (_handle401(r.status)) throw new Error('登录已失效，请重新登录')
  if (!r.ok) throw new Error(`API ${path} returned ${r.status}`)
  const body = await r.json()
  if (!body.success) throw new Error(body.error ?? 'API error')
  return body.data as T
}

// ── Platform SDK namespaces ─────────────────────────────────────────

export const auth = {
  async getCurrentUser(): Promise<CurrentUser> {
    return apiGet<CurrentUser>('/current-user')
  },
  hasPermission(permission: string): boolean {
    return hasPermission(permission)
  },
}

export const files = {
  async list(params: { folder_id?: number; page?: number; page_size?: number } = {}): Promise<FileListPage> {
    const qs = new URLSearchParams()
    if (params.folder_id !== undefined) qs.set('folder_id', String(params.folder_id))
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    return apiGet<FileListPage>(`/files/list?${qs.toString()}`)
  },
  async search(params: { keyword?: string; extension?: string; page?: number; page_size?: number } = {}): Promise<FileSearchPage> {
    const qs = new URLSearchParams()
    if (params.keyword) qs.set('keyword', params.keyword)
    if (params.extension) qs.set('extension', params.extension)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    return apiGet<FileSearchPage>(`/files/search?${qs.toString()}`)
  },
  async detail(fileId: number): Promise<FileDetail> {
    return apiGet<FileDetail>(`/files/detail/${fileId}`)
  },
  async upload(file: File, options?: { folder_id?: number }): Promise<UploadResult> {
    const form = new FormData()
    form.append('file', file)
    if (options?.folder_id) form.append('folder_id', String(options.folder_id))
    const url = getApiUrl('/files/upload')
    const r = await fetch(url, { method: 'POST', headers: authHeaders(), body: form })
    if (_handle401(r.status)) throw new Error('登录已失效，请重新登录')
    if (!r.ok) throw new Error(`Upload returned ${r.status}`)
    const body = await r.json()
    if (!body.success) throw new Error(body.error ?? 'Upload error')
    return body.data as UploadResult
  },
  downloadUrl(fileId: number): string {
    return getApiUrl(`/files/download/${fileId}`)
  },
  async preview(fileId: number): Promise<unknown> {
    return apiGet<unknown>(`/files/preview/${fileId}`)
  },
  async receivedShares(params: { page?: number; page_size?: number } = {}): Promise<FileSharePage> {
    const qs = new URLSearchParams()
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    return apiGet<FileSharePage>(`/files/share/received?${qs.toString()}`)
  },
  async checkAccess(fileId: number): Promise<FileAccessResult> {
    return apiGet<FileAccessResult>(`/files/share/check/${fileId}`)
  },
  getOpenPayload(): FileOpenPayload | null {
    return (window as unknown as Record<string, unknown>).__MODULE_OPEN_FILE_PAYLOAD__ as FileOpenPayload ?? null
  },
}

export const office = {
  async getStatus(fileId: number): Promise<OfficeStatus> {
    return apiGet<OfficeStatus>(`/office/status/${fileId}`)
  },
  async createPackage(payload: { file_id: number; format_type: string }): Promise<OfficePackage> {
    return apiPost<OfficePackage>('/office/package', payload)
  },
  async getPackage(packageId: number): Promise<OfficePackage> {
    return apiGet<OfficePackage>(`/office/package/${packageId}`)
  },
  async listVersions(packageId: number): Promise<OfficeVersion[]> {
    return apiGet<OfficeVersion[]>(`/office/package/${packageId}/versions`)
  },
}

export const gateway = {
  async listModels(): Promise<ModelProfile[]> {
    return apiGet<ModelProfile[]>('/gateway/models')
  },
  async health(): Promise<ModelHealth> {
    return apiGet<ModelHealth>('/gateway/health')
  },
  async chat(payload: { messages: Array<{ role: string; content: string }>; profile_key?: string }): Promise<ChatResult> {
    return apiPost<ChatResult>('/gateway/chat', payload)
  },
  async chatStream(payload: { messages: Array<{ role: string; content: string }>; profile_key?: string }): Promise<ReadableStream<Uint8Array>> {
    const url = getApiUrl('/gateway/chat-stream')
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    })
    if (_handle401(r.status)) throw new Error('登录已失效，请重新登录')
    if (!r.ok) throw new Error(`Chat stream returned ${r.status}`)
    if (!r.body) throw new Error('No response body for stream')
    return r.body
  },
  async embedding(payload: { texts: string[]; model?: string }): Promise<EmbeddingResult> {
    return apiPost<EmbeddingResult>('/gateway/embedding', payload)
  },
  async rerank(payload: { query: string; documents: string[]; model?: string }): Promise<RerankResult> {
    return apiPost<RerankResult>('/gateway/rerank', payload)
  },
}

export const tasks = {
  async submit(payload: { module: string; task_type: string; parameters?: Record<string, unknown>; priority?: number }): Promise<TaskInfo> {
    return apiPost<TaskInfo>('/tasks/submit', payload)
  },
  async get(taskId: number): Promise<TaskInfo> {
    return apiGet<TaskInfo>(`/tasks/${taskId}`)
  },
  async cancel(taskId: number): Promise<void> {
    await apiPost<void>(`/tasks/${taskId}/cancel`)
  },
  async retry(taskId: number): Promise<void> {
    await apiPost<void>(`/tasks/${taskId}/retry`)
  },
}

export const notifications = {
  async send(payload: { title: string; content?: string; notification_type?: string }): Promise<void> {
    await apiPost<void>('/notifications/module', payload)
  },
}

export const logs = {
  async info(action: string, message: string, data?: unknown): Promise<void> {
    await apiPost<void>('/logs/module', { level: 'info', action, message, data })
  },
  async error(action: string, message: string, data?: unknown): Promise<void> {
    await apiPost<void>('/logs/module', { level: 'error', action, message, data })
  },
  async frontendError(payload: { url?: string; status_code?: number; error_message?: string; page_path?: string }): Promise<void> {
    await apiPost<void>('/logs/frontend-error', payload)
  },
}

export const settings = {
  async get<T = unknown>(key: string, defaultValue?: T): Promise<T | undefined> {
    return (getModuleSetting<T>(key, defaultValue) as T) ?? defaultValue
  },
  async set<T = unknown>(_key: string, _value: T): Promise<void> {
  },
  async all(): Promise<Record<string, unknown>> {
    return _config?.module_settings ?? {}
  },
}

export const modules = {
  async call(targetModule: string, action: string, parameters: Record<string, unknown> = {}): Promise<unknown> {
    return apiPost<unknown>('/modules/call', { target_module: targetModule, action, parameters })
  },
  async capabilities(): Promise<string[]> {
    return apiGet<string[]>('/modules/capabilities')
  },
  /** 打开另一个模块的应用窗口（框架模式下可用） */
  openApp(appKey: string, params?: Record<string, unknown>): string | null {
    const wm = (window as unknown as Record<string, unknown>).__HSWZ_WINDOW_MANAGER__ as {
      openWindow: (appKey: string, payload?: unknown) => string | null
    } | undefined
    if (wm) return wm.openWindow(appKey, params)
    console.warn('[runtime] openApp: windowManager not available (not in framework mode)')
    return null
  },
}

// ── Unified platform export ─────────────────────────────────────────

export const platform = {
  auth,
  files,
  office,
  gateway,
  tasks,
  notifications,
  logs,
  settings,
  modules,
}
