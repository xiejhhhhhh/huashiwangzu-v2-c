import {
  apiDelete as runtimeApiDelete,
  apiGet as runtimeApiGet,
  apiPost as runtimeApiPost,
} from '../runtime'

export const apiGet = runtimeApiGet
export const apiPost = runtimeApiPost
export const apiDelete = runtimeApiDelete

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
  source_available: boolean
  source_state: string
}

export interface FrameworkFolder {
  id: number
  name: string
  parent_id: number | null
  created_at: string
  updated_at: string
}

export interface FrameworkFile {
  id: number
  name: string
  extension?: string | null
  size: number
  parent_id?: number | null
  is_folder: boolean
  created_at?: string | null
}

export interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface FileTreeNode {
  id: number
  node_key: string
  name: string
  parent_id: number | null
  is_folder: boolean
  children: FileTreeNode[]
  // 知识库状态
  kb_doc_id?: number
  kb_status?: string
  // 运行时辅助（渲染用）
  _depth?: number
  _open?: boolean
  _ext?: string
  _pct?: number | null
  _created_at?: string
  _render_key?: string
}

export interface ProgressStage {
  key: string
  label: string
  done: number
  total: number
  percent: number
  status: 'done' | 'running' | 'pending' | 'failed' | 'degraded' | 'paused' | 'source_unavailable'
  count?: number
}

export interface DocumentProgress {
  document_id: number
  filename: string
  total_pages: number
  overall_status: 'done' | 'running' | 'pending' | 'failed' | 'degraded' | 'paused' | 'source_unavailable'
  overall_percent: number
  current_stage: string
  source_available?: boolean
  source_state?: string
  stages: ProgressStage[]
}

export interface IngestStageStatus {
  status: string
  ready: boolean
  count?: number
  semantic?: 'done_with_results' | 'done_empty' | 'skipped' | 'paused'
  reason?: string | null
  node_count?: number
  chunk_entity_count?: number
}

export interface KnowledgeIngestStatus {
  document_id: number
  file_id: number
  filename: string
  source_available: boolean
  source_state: string
  stage: string
  status: string
  pipeline_status: string
  task_status?: string | null
  parse_status: string
  vector_status: string
  raw_status: string
  fusion_status: string
  stage_summary: Record<string, IngestStageStatus>
  search_ready: boolean
  deep_ready: boolean
  last_error?: string | null
  next_action: string
}

export type ExportFormat = 'markdown' | 'html' | 'json'

export interface ExportResult {
  success: boolean
  format: ExportFormat
  content: string
  filename: string
  document_id: number
  metadata?: {
    document_id: number
    title: string
    format: ExportFormat
    source_status: string
    search_ready: boolean
    deep_ready: boolean
    block_count: number
    evidence_count: number
    export_source: string
  }
  error?: string
}

export interface PendingCountResult {
  pending_count: number
}

export interface GovernanceCandidateList {
  items: GovernanceCandidate[]
  total: number
  page: number
  page_size: number
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
  labels_json?: {
    business_tags?: string[]
    usage_tags?: string[]
    content_boundaries?: string[]
    business_objects?: Array<{ name?: string; type?: string; evidence_pages?: number[] }>
    evidence?: Array<{ label?: string; pages?: number[]; excerpt?: string }>
  }
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
  file_id?: number | null
  source_file_id?: number | null
  page: number | null
  section?: string | null
  paragraph?: number | null
  block_type: string
  text: string
  score: number
  rrf_score: number
  document_name?: string
  source_file?: string
  source_module?: string
  source_type?: string
  retrieval_source?: string
  mime_type?: string
  extension?: string
  content_package_id?: number | null
  block_id?: string | null
  explain?: {
    retrieval_source?: string
    score?: number
    rrf_score?: number
    kw_score?: number
    vec_score?: number
    kw_rank?: number | null
    vec_rank?: number | null
    final_rank?: number
    source_file_id?: number | null
    source_file?: string
    page?: number | null
    section?: string | null
    paragraph?: number | null
  }
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

// ── 五层链路专用接口 ──────────────────────────────
export function startPipeline(documentId: number): Promise<{ task_id: number; status: string }> {
  return apiPost('/knowledge/documents/full-pipeline', { document_id: documentId })
}

export function getProgress(documentId: number): Promise<DocumentProgress> {
  return apiGet(`/knowledge/documents/${documentId}/progress`)
}

export function getIngestStatus(documentId: number): Promise<KnowledgeIngestStatus> {
  return apiGet(`/knowledge/documents/${documentId}/ingest-status`)
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

export function exportDocument(documentId: number, format: ExportFormat): Promise<ExportResult> {
  return apiPost<ExportResult>('/knowledge/documents/export', { document_id: documentId, format })
}

export function getPendingCount(): Promise<PendingCountResult> {
  return apiGet<PendingCountResult>('/knowledge/governance/pending-count')
}

export function getGovernanceCandidates(pageSize = 5): Promise<GovernanceCandidateList> {
  return apiGet<GovernanceCandidateList>(`/knowledge/governance/candidates?audit_status=pending&page=1&page_size=${pageSize}`)
}

/** JSON 字段可能以字符串返回,统一解析为对象/数组 */
export function parseJsonField<T>(value: unknown, fallback: T): T {
  if (value == null) return fallback
  if (typeof value === 'string') {
    try { return JSON.parse(value) as T } catch { return fallback }
  }
  return value as T
}

// ── 框架文件树（桌面路径镜像） ──────────────────────────

export function getFileTree(): Promise<FrameworkFolder[]> {
  return apiGet<FrameworkFolder[]>('/files/tree')
}

export function listKnowledgeDocuments(page = 1, pageSize = 100): Promise<PaginatedResult<KnowledgeDocument>> {
  return apiGet<PaginatedResult<KnowledgeDocument>>(`/knowledge/documents?page=${page}&page_size=${pageSize}`)
}

export function getFileList(folderId: number, page = 1, pageSize = 200): Promise<PaginatedResult<FrameworkFile>> {
  return apiGet<PaginatedResult<FrameworkFile>>(`/files/list?folder_id=${folderId}&page=${page}&page_size=${pageSize}`)
}

/** 将框架文件夹平铺列表递归构建为树 */
export function buildFolderTree(folders: FrameworkFolder[]): FileTreeNode[] {
  const map = new Map<number, FileTreeNode>()
  const roots: FileTreeNode[] = []
  for (const f of folders) {
    map.set(f.id, {
      id: f.id,
      node_key: `folder:${f.id}`,
      name: f.name,
      parent_id: f.parent_id,
      is_folder: true,
      children: [],
    })
  }
  for (const f of folders) {
    const node = map.get(f.id)!
    if (f.parent_id && map.has(f.parent_id)) {
      map.get(f.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

// ── 全局知识网络 ──────────────────────────────────────

export interface RelationGraphNode {
  id: number
  label: string
  type: string
}

export interface RelationGraphEdge {
  source: number
  target: number
  relation_type: string
  similarity_score: number
  shared_entities?: string[]
  weight?: number
}

export interface RelationGraph {
  nodes: RelationGraphNode[]
  edges: RelationGraphEdge[]
}

export function getRelationGraph(): Promise<RelationGraph> {
  return apiGet<RelationGraph>('/knowledge/relation-graph')
}

export interface EntityGraphNode {
  id: number
  label: string
  category?: string
  type?: string
  weight?: number
}

export interface EntityGraphEdge {
  source: number
  target: number
  weight?: number
  similarity_score?: number
  relation?: string
}

export interface EntityGraph {
  nodes: EntityGraphNode[]
  edges: EntityGraphEdge[]
}

export async function getEntityGraph(): Promise<EntityGraph> {
  return apiGet<EntityGraph>('/knowledge/entity-graph')
}

export interface DocProgressEntry {
  id: number
  filename: string
  total_pages: number
  raw_status: string
  fusion_status: string
  parse_status: string
  created_at: string
  source_available?: boolean
  source_state?: string
}

export interface DashboardStats {
  total_documents: number
  completed_documents: number
  running_documents: number
  failed_documents: number
  source_unavailable_documents?: number
  total_entities: number
  total_graph_relations: number
  total_file_relations: number
  duplicate_entity_count: number
  duplicate_entity_groups: Array<{ name: string; count: number }>
  entity_category_distribution: Record<string, number>
  document_progresses: DocProgressEntry[]
  stuck_documents: DocProgressEntry[]
  recent_completions: Array<{ id: number; filename: string; completed_at: string }>
}

export function getDashboardStats(): Promise<DashboardStats> {
  return apiGet<DashboardStats>('/knowledge/dashboard/stats')
}
