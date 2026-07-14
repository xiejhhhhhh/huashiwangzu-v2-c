/**
 * 模型路由模块 —— API 调用封装
 * 所有请求前缀 /api/model-router（BASE 拼接后由 runtime 补上 /api）
 */
import { apiGet, apiPost, apiPut, apiDelete } from '../runtime'

// ── 类型定义 ─────────────────────────────────────────────

export interface ProfileDetail {
  provider: string
  model: string
  temperature: number
  max_tokens: number
  context_budget: number
}

export interface RouterNode {
  id: string
  name: string
  group: string
  model_type: string
  current_profile: string
  profile_detail: ProfileDetail
  available_profiles: string[]
  fallback_chain: string[]
  health: 'ok' | 'degraded' | 'down'
}

export interface NodeUpdatePayload {
  profile_key: string
  temperature?: number
  max_tokens?: number
  context_budget?: number
  fallback_chain?: string[]
}

export interface ProviderItem {
  key: string
  type: string
  api_url: string
  api_key_env: string
  description: string
}

export interface ProviderTestResult {
  success: boolean
  latency_ms?: number
  error?: string
}

export interface ModelProfileItem {
  profile_key: string
  model_type: string
  provider: string
  model: string
  temperature?: number
  max_tokens?: number
  deprecated?: boolean
  [key: string]: unknown
}

export interface ReloadResult {
  status: string
  profiles?: number
  default?: unknown
}

const BASE = '/model-router'

// ── 调用节点 ─────────────────────────────────────────────

export const nodes = {
  list: () => apiGet<{ nodes: RouterNode[] }>(`${BASE}/nodes`),
  update: (nodeId: string, data: NodeUpdatePayload) =>
    apiPut<RouterNode>(`${BASE}/nodes/${nodeId}`, data),
}

// ── 提供商管理 ─────────────────────────────────────────

export const providers = {
  list: () => apiGet<{ providers: ProviderItem[] }>(`${BASE}/providers`),
  create: (data: ProviderItem) => apiPost<ProviderItem>(`${BASE}/providers`, data),
  update: (key: string, data: Partial<ProviderItem>) =>
    apiPut<ProviderItem>(`${BASE}/providers/${key}`, data),
  delete: (key: string) => apiDelete<{ deleted: boolean }>(`${BASE}/providers/${key}`),
  test: (key: string) => apiPost<ProviderTestResult>(`${BASE}/providers/${key}/test`),
}

// ── 模型档案 ─────────────────────────────────────────────

export const profiles = {
  list: () => apiGet<{ profiles: Record<string, ModelProfileItem[]> }>(`${BASE}/profiles`),
  create: (data: ModelProfileItem) => apiPost<ModelProfileItem>(`${BASE}/profiles`, data),
  update: (key: string, data: Partial<ModelProfileItem>) =>
    apiPut<ModelProfileItem>(`${BASE}/profiles/${key}`, data),
  delete: (key: string) => apiDelete<{ deleted: boolean }>(`${BASE}/profiles/${key}`),
}

// ── 重载配置 ─────────────────────────────────────────────

export const reload = {
  trigger: () => apiPost<ReloadResult>(`${BASE}/reload`),
}
