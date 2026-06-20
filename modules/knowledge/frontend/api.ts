import { getApiUrl } from '../runtime'

export interface KnowledgeDocument {
  id: number
  file_id: number
  filename: string
  extension: string
  file_size: number
  parse_status: string
  vector_status: string
  raw_status?: string
  fusion_status?: string
  total_chunks: number
  total_pages: number
  parse_error: string | null
}

export interface ProgressStage {
  key: string
  label: string
  done: number
  total: number
  percent: number
  status: 'done' | 'running' | 'pending'
  count?: number
}

export interface DocumentProgress {
  document_id: number
  filename: string
  total_pages: number
  overall_status: 'done' | 'running' | 'pending' | 'failed'
  overall_percent: number
  current_stage: string
  stages: ProgressStage[]
}

export interface FusionPage {
  page: number
  page_title: string | null
  fused_text: string
  page_summary: string
  confidence: number
  conflicts: Array<{ type?: string; detail?: string }>
}

export interface DocumentProfile {
  subject?: string
  doc_type?: string
  doc_summary?: string
  core_conclusions?: string
  applicable_scenarios?: string
  key_entities?: Array<{ name: string; type?: string }>
  chapter_structure?: Array<{ title?: string; page?: number; summary?: string }>
  confidence?: number
}

export interface FileRelation {
  source_document_id: number
  target_document_id: number
  relation_type: string
  similarity_score: number
  evidence?: string | null
  target_filename?: string
  source_filename?: string
}

export interface ChunkItem {
  id: number
  document_id: number
  page: number | null
  chunk_index: number
  block_type: string
  text: string
  keywords: string | null
}

export interface SearchResult {
  chunk_id: number
  document_id: number
  page: number | null
  block_type: string
  text: string
  score: number
  rrf_score: number
}

export interface EntityItem {
  id: number
  name: string
  category: string
  description: string | null
  status: string
}

export interface GovernanceCandidate {
  id: number
  document_id: number
  entity_name: string
  category: string
  excerpt: string
  confidence: number
  audit_status: string
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('v2_auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(getApiUrl(path), { headers: authHeaders() })
  const body = await response.json()
  if (!response.ok || !body.success) throw new Error(body.error || `HTTP ${response.status}`)
  return body.data as T
}

export async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(getApiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  const body = await response.json()
  if (!response.ok || !body.success) throw new Error(body.error || `HTTP ${response.status}`)
  return body.data as T
}

export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(getApiUrl(path), { method: 'DELETE', headers: authHeaders() })
  const body = await response.json()
  if (!response.ok || !body.success) throw new Error(body.error || `HTTP ${response.status}`)
  return body.data as T
}

// ── 五层链路专用接口 ──────────────────────────────
export function startPipeline(documentId: number): Promise<{ task_id: number; status: string }> {
  return apiPost('/knowledge/documents/full-pipeline', { document_id: documentId })
}

export function getProgress(documentId: number): Promise<DocumentProgress> {
  return apiGet(`/knowledge/documents/${documentId}/progress`)
}

export function getProgressBatch(documentIds: number[]): Promise<Record<string, DocumentProgress>> {
  return apiPost('/knowledge/documents/progress-batch', { document_ids: documentIds })
}

export function getFusions(documentId: number): Promise<{ items: FusionPage[] }> {
  return apiGet(`/knowledge/documents/${documentId}/fusions`)
}

export function getProfile(documentId: number): Promise<DocumentProfile | null> {
  return apiGet(`/knowledge/documents/${documentId}/profile`)
}

export async function getRelations(documentId: number): Promise<FileRelation[]> {
  const data = await apiGet<{ relations: FileRelation[] } | FileRelation[]>(
    `/knowledge/documents/${documentId}/relations`,
  )
  return Array.isArray(data) ? data : (data.relations ?? [])
}

/** JSON 字段可能以字符串返回,统一解析为对象/数组 */
export function parseJsonField<T>(value: unknown, fallback: T): T {
  if (value == null) return fallback
  if (typeof value === 'string') {
    try { return JSON.parse(value) as T } catch { return fallback }
  }
  return value as T
}
