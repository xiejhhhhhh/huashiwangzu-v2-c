/**
 * Module Runtime — shared middle layer between sandbox and main framework.
 *
 * Each module copies this file into modules/{name}/runtime/index.ts.
 * All API paths, permissions, and settings are read through this layer,
 * so module code never hardcodes framework-specific values.
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

export interface PatchPreview {
  diff: unknown
  risk_level: string
}

export interface PatchResult {
  success: boolean
  new_version_id: number | null
  error: string | null
}

export interface RollbackResult {
  success: boolean
  restored_version_id: number | null
  error: string | null
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

function authHeaders(): HeadersInit {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiGet<T>(path: string): Promise<T> {
  const url = getApiUrl(path)
  const r = await fetch(url, { headers: authHeaders() })
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
  if (!r.ok) throw new Error(`API ${path} returned ${r.status}`)
  const body = await r.json()
  if (!body.success) throw new Error(body.error ?? 'API error')
  return body.data as T
}

// ── Platform SDK namespaces ─────────────────────────────────────────

export const auth = {
  /** Get current authenticated user info */
  async getCurrentUser(): Promise<CurrentUser> {
    return apiGet<CurrentUser>('/current-user')
  },
  /** Check if a specific permission is granted */
  hasPermission(permission: string): boolean {
    return hasPermission(permission)
  },
}

export const files = {
  /** List files and folders in a given folder */
  async list(params: { folder_id?: number; page?: number; page_size?: number } = {}): Promise<FileListPage> {
    const qs = new URLSearchParams()
    if (params.folder_id !== undefined) qs.set('folder_id', String(params.folder_id))
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    return apiGet<FileListPage>(`/files/list?${qs.toString()}`)
  },
  /** Search files and folders */
  async search(params: { keyword?: string; extension?: string; page?: number; page_size?: number } = {}): Promise<FileSearchPage> {
    const qs = new URLSearchParams()
    if (params.keyword) qs.set('keyword', params.keyword)
    if (params.extension) qs.set('extension', params.extension)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    return apiGet<FileSearchPage>(`/files/search?${qs.toString()}`)
  },
  /** Get file detail */
  async detail(fileId: number): Promise<FileDetail> {
    return apiGet<FileDetail>(`/files/detail/${fileId}`)
  },
  /** Upload a file */
  async upload(file: File, options?: { folder_id?: number }): Promise<UploadResult> {
    const form = new FormData()
    form.append('file', file)
    if (options?.folder_id) form.append('folder_id', String(options.folder_id))
    const url = getApiUrl('/files/upload')
    const r = await fetch(url, { method: 'POST', headers: authHeaders(), body: form })
    if (!r.ok) throw new Error(`Upload returned ${r.status}`)
    const body = await r.json()
    if (!body.success) throw new Error(body.error ?? 'Upload error')
    return body.data as UploadResult
  },
  /** Get download URL for a file */
  downloadUrl(fileId: number): string {
    return getApiUrl(`/files/download/${fileId}`)
  },
  /** Get preview data for a file */
  async preview(fileId: number): Promise<unknown> {
    return apiGet<unknown>(`/files/preview/${fileId}`)
  },
  /** Get files shared with the current user */
  async receivedShares(params: { page?: number; page_size?: number } = {}): Promise<FileSharePage> {
    const qs = new URLSearchParams()
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    return apiGet<FileSharePage>(`/files/share/received?${qs.toString()}`)
  },
  /** Check if the current user can access a given file */
  async checkAccess(fileId: number): Promise<FileAccessResult> {
    return apiGet<FileAccessResult>(`/files/share/check/${fileId}`)
  },
  /** Get the FileOpenPayload injected by the framework when a file is opened */
  getOpenPayload(): FileOpenPayload | null {
    return (window as unknown as Record<string, unknown>).__MODULE_OPEN_FILE_PAYLOAD__ as FileOpenPayload ?? null
  },
}

export const office = {
  /** Get Office document status for a file */
  async getStatus(fileId: number): Promise<OfficeStatus> {
    return apiGet<OfficeStatus>(`/office/status/${fileId}`)
  },
  /** Create a new JSON package for a file */
  async createPackage(payload: { file_id: number; format_type: string }): Promise<OfficePackage> {
    return apiPost<OfficePackage>('/office/package', payload)
  },
  /** Get a JSON package by ID */
  async getPackage(packageId: number): Promise<OfficePackage> {
    return apiGet<OfficePackage>(`/office/package/${packageId}`)
  },
  /** List all versions of a JSON package */
  async listVersions(packageId: number): Promise<OfficeVersion[]> {
    return apiGet<OfficeVersion[]>(`/office/package/${packageId}/versions`)
  },
  /** Preview a patch before applying it */
  async previewPatch(payload: unknown): Promise<PatchPreview> {
    return apiPost<PatchPreview>('/office/patch/preview', payload)
  },
  /** Apply a patch */
  async applyPatch(payload: unknown): Promise<PatchResult> {
    return apiPost<PatchResult>('/office/patch/apply', payload)
  },
  /** Rollback to a previous version */
  async rollback(payload: unknown): Promise<RollbackResult> {
    return apiPost<RollbackResult>('/office/rollback', payload)
  },
}

export const gateway = {
  /** List available AI model profiles */
  async listModels(): Promise<ModelProfile[]> {
    return apiGet<ModelProfile[]>('/gateway/models')
  },
  /** Check health of all model providers */
  async health(): Promise<ModelHealth> {
    return apiGet<ModelHealth>('/gateway/health')
  },
  /** Send a chat completion request */
  async chat(payload: { messages: Array<{ role: string; content: string }>; profile_key?: string }): Promise<ChatResult> {
    return apiPost<ChatResult>('/gateway/chat', payload)
  },
  /** Send a streaming chat completion request (returns ReadableStream) */
  async chatStream(payload: { messages: Array<{ role: string; content: string }>; profile_key?: string }): Promise<ReadableStream<Uint8Array>> {
    const url = getApiUrl('/gateway/chat-stream')
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    })
    if (!r.ok) throw new Error(`Chat stream returned ${r.status}`)
    if (!r.body) throw new Error('No response body for stream')
    return r.body
  },
  /** Get embeddings for text */
  async embedding(payload: { texts: string[]; model?: string }): Promise<EmbeddingResult> {
    return apiPost<EmbeddingResult>('/gateway/embedding', payload)
  },
  /** Rerank documents */
  async rerank(payload: { query: string; documents: string[]; model?: string }): Promise<RerankResult> {
    return apiPost<RerankResult>('/gateway/rerank', payload)
  },
}

export const tasks = {
  /** Submit a background task */
  async submit(payload: { module: string; task_type: string; parameters?: Record<string, unknown>; priority?: number }): Promise<TaskInfo> {
    return apiPost<TaskInfo>('/tasks/submit', payload)
  },
  /** Get task info */
  async get(taskId: number): Promise<TaskInfo> {
    return apiGet<TaskInfo>(`/tasks/${taskId}`)
  },
  /** Cancel a pending task */
  async cancel(taskId: number): Promise<void> {
    await apiPost<void>(`/tasks/${taskId}/cancel`)
  },
  /** Retry a failed task */
  async retry(taskId: number): Promise<void> {
    await apiPost<void>(`/tasks/${taskId}/retry`)
  },
}

export const notifications = {
  /** Send a module notification */
  async send(payload: { title: string; content?: string; notification_type?: string }): Promise<void> {
    await apiPost<void>('/notifications/module', payload)
  },
}

export const logs = {
  /** Write an informational log entry */
  async info(action: string, message: string, data?: unknown): Promise<void> {
    await apiPost<void>('/logs/module', { level: 'info', action, message, data })
  },
  /** Write an error log entry */
  async error(action: string, message: string, data?: unknown): Promise<void> {
    await apiPost<void>('/logs/module', { level: 'error', action, message, data })
  },
  /** Send a frontend error report */
  async frontendError(payload: { url?: string; status_code?: number; error_message?: string; page_path?: string }): Promise<void> {
    await apiPost<void>('/logs/frontend-error', payload)
  },
}

export const settings = {
  /** Get a module setting by key */
  async get<T = unknown>(key: string, defaultValue?: T): Promise<T | undefined> {
    return (getModuleSetting<T>(key, defaultValue) as T) ?? defaultValue
  },
  /** Set a module setting */
  async set<T = unknown>(_key: string, _value: T): Promise<void> {
    // Persisted via HTTP when available; current implementation uses in-memory config
  },
  /** Get all module settings */
  async all(): Promise<Record<string, unknown>> {
    return _config?.module_settings ?? {}
  },
}

export const modules = {
  /** 调用另一个模块对外公开的能力（经框架统一通路 + 权限 + 审计） */
  async call(targetModule: string, action: string, parameters: Record<string, unknown> = {}): Promise<unknown> {
    return apiPost<unknown>('/modules/call', { target_module: targetModule, action, parameters })
  },
  /** 列出当前已注册的跨模块能力（module:action 列表） */
  async capabilities(): Promise<string[]> {
    return apiGet<string[]>('/modules/capabilities')
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
