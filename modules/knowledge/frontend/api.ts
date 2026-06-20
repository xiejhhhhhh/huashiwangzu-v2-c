import { getApiUrl } from '../runtime'

export interface KnowledgeDocument {
  id: number
  file_id: number
  filename: string
  extension: string
  file_size: number
  parse_status: string
  vector_status: string
  total_chunks: number
  total_pages: number
  parse_error: string | null
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
