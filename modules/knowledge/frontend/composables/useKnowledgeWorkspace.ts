import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { authHeaders, getApiUrl, initRuntime, platform } from '../../runtime'
import {
  apiDelete,
  apiGet,
  apiPost,
  exportDocument,
  getFileList,
  getFusions,
  getIngestStatus,
  getKnowledgeDocument,
  getProfile,
  getProgress,
  getProgressBatch,
  getRelations,
  listKnowledgeDocumentsByFileIds,
  parseJsonField,
  type DocumentProfile,
  type DocumentProgress,
  type ExportFormat,
  type FileRelation,
  type FileTreeNode,
  type FusionPage,
  type KnowledgeDocument,
  type KnowledgeIngestStatus,
  type ProgressStage,
  type SearchResult,
} from '../api'
import type { KnowledgeEntryProps } from '../types'

export function useKnowledgeWorkspace(props: KnowledgeEntryProps) {
  const documents = ref<KnowledgeDocument[]>([])
  const active = ref<KnowledgeDocument | null>(null)
  const showWorkspace = ref(false)
  const showDashboard = ref(false)
  const userRole = ref('viewer')
  const isAdminOrEditor = computed(() => userRole.value === 'admin' || userRole.value === 'editor')
  const activeId = computed(() => active.value?.id ?? null)
  const keyword = ref('')
  const tab = ref<'overview' | 'reader' | 'relation' | 'search'>('overview')
  const showGovernanceFromPayload = computed(() => props.showGovernance === true)

  // ── 文件树 ──
  const fileTree = ref<FileTreeNode[]>([])
  const treeLoading = ref(false)
  const treeError = ref('')
  const folderOpenState = ref<Record<number, boolean>>({})
  const folderFiles = ref<Record<number, FileTreeNode[]>>({})  // folder_id -> loaded child folders and files
  const kbDocMap = ref<Record<number, KnowledgeDocument>>({})
  const liveProgressMap = ref<Record<number, DocumentProgress>>({})

  const FILE_PAGE_SIZE = 200
  const PROGRESS_BATCH_SIZE = 100
  const RUNNING_STAGE_STATUSES = new Set(['running', 'collecting', 'parsing', 'fusing', 'queued', 'inflight'])
  const FAILED_STAGE_STATUSES = new Set(['failed', 'error', 'source_unavailable'])
  const DEGRADED_STAGE_STATUSES = new Set(['degraded', 'paused'])

  function documentStageStatuses(doc: KnowledgeDocument): string[] {
    return [
      doc.raw_status || 'pending',
      doc.fusion_status || 'pending',
      doc.profile_status || 'pending',
      doc.graph_status || 'pending',
      doc.relation_status || 'pending',
    ]
  }

  function deriveDocumentStatus(doc: KnowledgeDocument): string {
    if (doc.source_available === false || doc.source_state === 'source_unavailable') return 'source_unavailable'
    const statuses = documentStageStatuses(doc)
    if (statuses.some(status => FAILED_STAGE_STATUSES.has(status))) return 'failed'
    if (statuses.some(status => RUNNING_STAGE_STATUSES.has(status))) return 'running'
    if (statuses.some(status => DEGRADED_STAGE_STATUSES.has(status))) return 'degraded'
    if (statuses.every(status => status === 'done' || status === 'skipped')) return 'done'
    return 'pending'
  }

  // ── 树节点状态/百分比实时派生（从 liveProgressMap 现查，不存静态快照） ──
  function getNodeLiveStatus(node: FileTreeNode): string | undefined {
    if (node.is_folder || !node.kb_doc_id) return undefined
    const lp = liveProgressMap.value[node.kb_doc_id]
    if (lp) {
      if (lp.overall_status === 'running') return 'running'
      if (lp.overall_status === 'done') return 'done'
      if (lp.overall_status === 'failed') return 'failed'
      if (lp.overall_status === 'degraded') return 'degraded'
      if (lp.overall_status === 'paused') return 'degraded'
      if (lp.overall_status === 'source_unavailable') return 'failed'
      return 'pending'
    }
    // 兜底：liveProgressMap 无记录时用 doc 粗状态字段
    const doc = kbDocMap.value[node.id]
    if (!doc) return undefined
    return deriveDocumentStatus(doc)
  }

  function getNodeLivePct(node: FileTreeNode): number | null {
    if (node.is_folder || !node.kb_doc_id) return null
    const lp = liveProgressMap.value[node.kb_doc_id]
    if (lp && lp.overall_status === 'running') return lp.overall_percent
    return null
  }

  async function toggleFolder(node: FileTreeNode) {
    const key = node.id
    const wasOpen = folderOpenState.value[key]
    folderOpenState.value[key] = !wasOpen
    // 展开时只加载当前文件夹的直接子节点。
    if (!wasOpen && !folderFiles.value[key]) {
      try {
        folderFiles.value[key] = await loadFolderChildren(key)
        await handshakeLoaded()
      } catch { folderFiles.value[key] = [] }
    }
  }

  const visibleTree = computed(() => {
    const kw = keyword.value.trim().toLowerCase()
    function flatten(nodes: FileTreeNode[], depth: number, parentPath = 'root'): FileTreeNode[] {
      const out: FileTreeNode[] = []
      nodes.forEach((n, index) => {
        const renderKey = `${parentPath}/${n.node_key}:${index}`
        const nameMatch = !kw || n.name.toLowerCase().includes(kw)
        // 合并子文件夹和已加载的文件，文件夹在前
        const fileKids = folderFiles.value[n.id] || []
        const seenKids = new Set<string>()
        const allKids = [...n.children, ...fileKids].filter((child) => {
          const childKey = `${child.is_folder ? 'folder' : 'file'}:${child.id}`
          if (seenKids.has(childKey)) return false
          seenKids.add(childKey)
          return true
        }).sort((a, b) => {
          if (a.is_folder !== b.is_folder) return a.is_folder ? -1 : 1
          if (!a.is_folder) return (b._created_at || '').localeCompare(a._created_at || '')
          return a.name.localeCompare(b.name)
        })
        const childFlat = allKids.length ? flatten(allKids, depth + 1, renderKey) : []
        const childMatch = childFlat.length > 0
        if (nameMatch || childMatch) {
          const open = kw ? true : !!folderOpenState.value[n.id]
          out.push({ ...n, _depth: depth, _open: open,
            _render_key: renderKey,
            kb_status: getNodeLiveStatus(n),
            _pct: getNodeLivePct(n),
          })
          if (open || kw) out.push(...childFlat)
        }
      })
      return out
    }
    return flatten(fileTree.value, 0)
  })

  function openWorkspace() {
    showWorkspace.value = true
    showDashboard.value = false
    active.value = null
  }

  function openDashboard() {
    showDashboard.value = true
    showWorkspace.value = false
    active.value = null
  }

  async function loadUserRole() {
    try {
      const data = await apiGet<{ role: string }>('/current-user')
      if (data?.role) userRole.value = data.role
    } catch { /* ignore */ }
  }

  function jumpToFirstRunning() {
    const runningId = Object.keys(liveProgressMap.value).find(k => liveProgressMap.value[Number(k)]?.overall_status === 'running')
    if (runningId) {
      const doc = documents.value.find(d => d.id === Number(runningId))
      if (doc) openDocument(doc)
    }
  }

  // ── 进度/分析 ──
  const progress = ref<DocumentProgress | null>(null)
  const ingestStatus = ref<KnowledgeIngestStatus | null>(null)
  const fusions = ref<FusionPage[]>([])
  const profile = ref<DocumentProfile | null>(null)
  const relations = ref<FileRelation[]>([])
  const resultLoadErrors = ref<{ fusions?: string; profile?: string; relations?: string }>({})
  const query = ref('')
  const searching = ref(false)
  const searched = ref(false)
  const searchResults = ref<SearchResult[]>([])
  const searchMetadataText = ref('')
  const exportFormat = ref<ExportFormat>('markdown')
  const exporting = ref(false)
  let pollTimer: number | null = null

  const analyzing = computed(() => progress.value?.overall_status === 'running')
  const runningCount = computed(() => Object.values(liveProgressMap.value).filter(p => p.overall_status === 'running').length)
  const hasResult = computed(() => progress.value?.overall_status === 'done' || progress.value?.overall_status === 'degraded' || fusions.value.length > 0)
  const showProgress = computed(() => !!progress.value && progress.value.overall_status !== 'done')
  const analyzeButtonText = computed(() => {
    if (analyzing.value) return '分析中…'
    if (progress.value?.overall_status === 'done') return '重新分析'
    if (progress.value?.overall_status === 'degraded') return '补跑分析'
    return '开始分析'
  })
	  const headStatusText = computed(() => { const p = progress.value; if (!p) return '尚未分析'; if (p.overall_status === 'done') return '分析完成'; if (p.overall_status === 'failed') return '分析出错'; if (p.overall_status === 'degraded') return '分析有缺损'; if (p.overall_status === 'paused') return '模型降级后已暂停'; if (p.overall_status === 'source_unavailable') return '源文件不可用'; if (p.overall_status === 'running') return p.current_stage + '…'; return '待分析' })
	  const progressHeadline = computed(() => { const p = progress.value; if (!p) return ''; if (p.overall_status === 'done') return '全部完成'; if (p.overall_status === 'failed') return '分析出错,可重新分析'; if (p.overall_status === 'degraded') return '分析有缺损,可重新分析'; if (p.overall_status === 'paused') return 'GPT5.5 降级后已按规则暂停，可检查后再继续'; if (p.overall_status === 'source_unavailable') return '源文件已删除或不可用'; return '正在「' + p.current_stage + '」' })
	  const progressHint = computed(() => { const p = progress.value; if (!p) return ''; if (p.overall_status === 'running') return '正在处理,可关闭页面,稍后回来会自动接着显示进度'; if (p.overall_status === 'paused') return '已保存当前阶段结果,后续可从断点继续或重跑深层分析'; if (p.overall_status === 'failed') return '已记录失败原因,可查看状态后重新分析'; if (p.overall_status === 'degraded') return '已保留可用结果,建议后续补跑缺损阶段'; if (p.overall_status === 'source_unavailable') return '源文件不可用,请恢复或重新上传后再继续'; if (p.overall_status === 'done') return '分析完成,下方查看结果'; return '等待进入分析队列' })
  const ringStyle = computed(() => { const pct = progress.value?.overall_percent ?? 0; return { background: `conic-gradient(#2395bc ${pct * 3.6}deg, #e6eef5 0deg)` } })
  const overallPercent = computed(() => Math.max(0, Math.min(100, progress.value?.overall_percent ?? 0)))
  const sourceUnavailable = computed(() => ingestStatus.value?.source_available === false || progress.value?.overall_status === 'source_unavailable')
  const canExport = computed(() => !!ingestStatus.value?.source_available && !!ingestStatus.value?.search_ready)
  const graphSemanticText = computed(() => {
    const graph = ingestStatus.value?.stage_summary.graph
    if (!graph) return '图谱暂无数据'
    if (graph.ready) return '图谱可用'
    if ((graph.count ?? 0) === 0 && (graph.chunk_entity_count ?? 0) === 0) {
      return '图谱暂无数据：当前文档未抽取到可用实体或关系，不影响搜索和导出。'
    }
    return '图谱生成中'
  })
  const ingestStatusLabel = computed(() => {
    const status = ingestStatus.value?.pipeline_status || progress.value?.overall_status || 'pending'
    if (status === 'source_unavailable') return '源文件不可用'
    if (status === 'deep_ready') return '深度分析完成'
    if (status === 'search_ready') return '可检索'
    if (status === 'failed') return '失败'
    if (status === 'degraded') return '部分完成'
    if (status === 'paused') return '已暂停'
    if (status === 'running') return '处理中'
    if (status === 'queued') return '等待中'
    return '待分析'
  })
  const statusClassForIngest = computed(() => {
    const status = ingestStatus.value?.pipeline_status || progress.value?.overall_status || 'pending'
    if (status === 'source_unavailable' || status === 'failed') return 'err'
    if (status === 'degraded' || status === 'paused') return 'warn'
    if (status === 'running' || status === 'queued') return 'busy'
    if (status === 'deep_ready' || status === 'search_ready') return 'ok'
    return ''
  })
  const ingestStatusHint = computed(() => {
    const status = ingestStatus.value
    if (!status) return ''
    if (!status.source_available) return sourceStateText(status.source_state)
    if (status.next_action === 'ready') return '可以搜索、问 AI 或导出资料内容。'
    if (status.next_action === 'review_model_degradation_before_resume') return 'GPT5.5 已降级，本轮已按规则暂停；可检查日志或重新触发深度分析。'
    if (status.next_action === 'wait_for_search_index') return '正在建立检索索引，请稍后再试。'
    if (status.next_action === 'wait_for_deep_analysis') return '检索已可用，深度分析仍在继续。'
    if (status.next_action.includes('retry')) return '可以查看失败原因后重新分析。'
    return '可以继续分析，让资料进入可检索状态。'
  })
  const profileEntities = computed(() => parseJsonField<Array<{ name: string }>>(profile.value?.key_entities, []).slice(0, 12))
  const profileChapters = computed(() => parseJsonField<Array<{ title?: string; page?: number }>>(profile.value?.chapter_structure, []))
  const profileBusinessTags = computed(() => {
    const labels = profile.value?.labels_json
    const tags = Array.isArray(labels?.business_tags) ? labels.business_tags : []
    return tags.filter((tag): tag is string => typeof tag === 'string' && tag.trim().length > 0).slice(0, 12)
  })

  function fileIcon(ext?: string): string { const e = (ext || '').toLowerCase(); if (e === 'pdf') return '📕'; if (['doc','docx'].includes(e)) return '📘'; if (['xls','xlsx'].includes(e)) return '📗'; if (['ppt','pptx'].includes(e)) return '📙'; if (['png','jpg','jpeg','gif','webp'].includes(e)) return '🖼'; return '📄' }
  function docName(id: number): string { return documents.value.find(d => d.id === id)?.filename || ('资料 #'+id) }
  function statusDotClass(status?: string): string { if (status === 'done') return 'ok'; if (status && RUNNING_STAGE_STATUSES.has(status)) return 'busy'; if (status && FAILED_STAGE_STATUSES.has(status)) return 'failed'; if (status && DEGRADED_STAGE_STATUSES.has(status)) return 'warn'; return 'idle' }
  function stageLabel(stage: string): string { const labels: Record<string, string> = { source: '源文件', parse: '解析', vector: '索引', raw: '原始采集', fusion: '页级融合', profile: '画像', graph: '图谱', relation: '关联', complete: '完成' }; return labels[stage] || stage }
  function sourceStateText(state: string): string { const labels: Record<string, string> = { source_file_deleted: '原始文件已删除或进入回收站。', source_file_missing: '原始文件路径不可用。', permission_denied: '当前账号没有访问原始文件的权限。', source_unavailable: '原始文件不可用。' }; return labels[state] || '原始文件不可用。' }
  function readableFailure(message: string): string { return message.replace(/^Document source file unavailable:\s*/i, '源文件不可用：') }
  function errorMessage(error: unknown, fallback: string): string {
    if (error instanceof Error && error.message) return error.message
    if (typeof error === 'string' && error.trim()) return error
    if (error && typeof error === 'object') {
      const value = error as { message?: unknown; error?: unknown; detail?: unknown; response?: { data?: { error?: unknown; message?: unknown } } }
      const nested = value.response?.data
      const message = value.message || value.error || value.detail || nested?.message || nested?.error
      if (typeof message === 'string' && message.trim()) return message
      try { return JSON.stringify(error) }
      catch { return fallback }
    }
    return fallback
  }
  function stepCount(s: ProgressStage): string { if (s.key === 'graph') return s.count ? `${s.count} 个实体` : (s.status === 'done' ? '完成' : '—'); if (s.key === 'relation') return s.count ? `${s.count} 条关联` : (s.status === 'done' ? '完成' : '—'); if (s.total <= 1) return s.status === 'done' ? '完成' : (s.status === 'running' ? '进行中' : '—'); return `${s.done}/${s.total}` }
  function confClass(c?: number): string { const v = c || 0; if (v >= 0.9) return 'high'; if (v >= 0.75) return 'mid'; return 'low' }
  function relPct(r: FileRelation): number { return Math.round((r.similarity_score || 0) * 100) }
  const analyzedDocCount = computed(() => {
    return documents.value.filter(d => {
      const lp = liveProgressMap.value[d.id]
      return lp?.overall_status === 'done' || (!lp && deriveDocumentStatus(d) === 'done')
    }).length
  })
  const failedDocumentCount = computed(() => documents.value.filter(doc => {
    const status = liveProgressMap.value[doc.id]?.overall_status || deriveDocumentStatus(doc)
    return status === 'failed' || status === 'source_unavailable'
  }).length)
  const pendingDocumentCount = computed(() => Math.max(0, documents.value.length - analyzedDocCount.value - runningCount.value - failedDocumentCount.value))
  const recentDocuments = computed(() => documents.value.slice(-8).reverse())
  function documentStatus(doc: KnowledgeDocument): string {
    return liveProgressMap.value[doc.id]?.overall_status || deriveDocumentStatus(doc)
  }
  function documentStatusText(doc: KnowledgeDocument): string {
    const status = documentStatus(doc)
    if (status === 'done') return '分析完成'
    if (status === 'running') return '分析中'
    if (status === 'failed' || status === 'source_unavailable') return '需要处理'
    if (status === 'degraded' || status === 'paused') return '部分完成'
    return '待分析'
  }
  const pendingPageRef = ref<number | undefined>(undefined)
  function escapeHtml(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  }
  function highlightText(text: string, q: string): string {
    const safe = escapeHtml(text || '')
    if (!q.trim()) return safe
    const terms = q.trim().split(/\s+/).filter(t => t.length >= 1)
    let result = safe
    for (const term of terms) {
      const escaped = escapeHtml(term)
      const re = new RegExp(`(${escaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
      result = result.replace(re, '<mark class="kw-highlight">$1</mark>')
    }
    return result
  }
  async function openBlobPath(path: string) {
    const url = getApiUrl(path)
    const response = await fetch(url, { headers: authHeaders() })
    if (!response.ok) throw new Error(`接口返回 ${response.status}`)
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    window.open(objectUrl, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  }
  async function openSearchSource(item: SearchResult) {
    if (!item.source_file_id) return
    try {
      await openBlobPath(`/files/preview/${item.source_file_id}`)
    } catch (e: unknown) {
      console.warn('[kb] open source failed:', e)
    }
  }
  async function downloadSearchSource(item: SearchResult) {
    if (!item.source_file_id) return
    try {
      await openBlobPath(`/files/download/${item.source_file_id}`)
    } catch (e: unknown) {
      console.warn('[kb] download source failed:', e)
    }
  }
  async function copySearchReference(item: SearchResult) {
    const payload = [
      item.source_module || 'knowledge',
      `document_id=${item.document_id}`,
      item.chunk_id ? `chunk_id=${item.chunk_id}` : '',
      item.source_file_id ? `source_file_id=${item.source_file_id}` : '',
      item.content_package_id ? `package_id=${item.content_package_id}` : '',
      item.page ? `page=${item.page}` : '',
    ].filter(Boolean).join(' | ')
    try {
      await navigator.clipboard.writeText(payload)
    } catch (e: unknown) {
      console.warn('[kb] copy reference failed:', e)
    }
  }
  function showSearchMetadata(item: SearchResult) {
    searchMetadataText.value = JSON.stringify({
      source_module: item.source_module || 'knowledge',
      file_id: item.file_id,
      source_file_id: item.source_file_id,
      document_id: item.document_id,
      chunk_id: item.chunk_id,
      package_id: item.content_package_id,
      block_id: item.block_id,
      page: item.page,
      section: item.section,
      paragraph: item.paragraph,
      score: item.score,
      source_file: item.source_file,
      query_plan: item.query_plan,
      explain: item.explain,
    }, null, 2)
  }
  async function jumpToSearchResult(item: SearchResult) {
    const doc = await ensureDocument(item.document_id)
    if (!doc) return
    pendingPageRef.value = item.page ?? undefined
    await openDocument(doc)
  }

  async function loadAllFilesInFolder(folderId: number): Promise<Awaited<ReturnType<typeof getFileList>>['items']> {
    const all: Awaited<ReturnType<typeof getFileList>>['items'] = []
    for (let page = 1; page <= 100; page += 1) {
      const data = await getFileList(folderId, page, FILE_PAGE_SIZE)
      all.push(...(data.items || []))
      if (all.length >= data.total || (data.items || []).length < FILE_PAGE_SIZE) break
    }
    return all
  }

  function mergeKnowledgeDocuments(nextDocs: KnowledgeDocument[]) {
    if (!nextDocs.length) return
    const docByFileId: Record<number, KnowledgeDocument> = { ...kbDocMap.value }
    const docById = new Map<number, KnowledgeDocument>()
    for (const doc of documents.value) docById.set(doc.id, doc)
    for (const doc of nextDocs) {
      docByFileId[doc.file_id] = doc
      docById.set(doc.id, doc)
    }
    kbDocMap.value = docByFileId
    documents.value = Array.from(docById.values())
  }

  async function attachKnowledgeStatus(nodes: FileTreeNode[]) {
    const fileIds = nodes.filter((node) => !node.is_folder).map((node) => node.id)
    const docs = await listKnowledgeDocumentsByFileIds(fileIds)
    mergeKnowledgeDocuments(docs)
    for (const node of nodes) {
      const doc = kbDocMap.value[node.id]
      if (doc) {
        node.kb_doc_id = doc.id
        node._ext = doc.extension || node._ext || ''
      }
    }
  }

  async function loadFolderChildren(folderId: number): Promise<FileTreeNode[]> {
    const items = await loadAllFilesInFolder(folderId)
    const children: FileTreeNode[] = items.map((f) => ({
      id: f.id,
      name: f.name,
      parent_id: folderId === 0 ? null : folderId,
      is_folder: f.is_folder,
      node_key: `${f.is_folder ? 'folder' : 'file'}:${f.id}`,
      children: [],
      _depth: 0,
      _open: false,
      _ext: f.extension || '',
      _pct: null,
      _created_at: f.created_at || '',
    }))
    await attachKnowledgeStatus(children)
    children.sort((a, b) => {
      if (a.is_folder !== b.is_folder) return a.is_folder ? -1 : 1
      if (!a.is_folder) return (b._created_at || '').localeCompare(a._created_at || '')
      return a.name.localeCompare(b.name)
    })
    return children
  }

  async function loadFileTree() {
    treeLoading.value = true
    treeError.value = ''
    try {
      fileTree.value = await loadFolderChildren(0)
      folderFiles.value = {}
      folderOpenState.value = {}
      await handshakeLoaded()
    } catch (e: unknown) {
      console.error('[kb] loadFileTree:', e)
      treeError.value = '知识库文件树加载失败：' + String((e as Error).message || e)
    } finally {
      treeLoading.value = false
    }
  }

  async function applyOpenPayload() {
    if (typeof props.documentId === 'number' && props.documentId > 0) {
      const doc = await ensureDocument(props.documentId)
      if (doc) {
        await openDocument(doc)
        return
      }
      openDashboard()
      return
    }
    if (props.view === 'dashboard') {
      openDashboard()
    } else if (props.view === 'workspace') {
      openWorkspace()
    }
  }

  /** 知识库支持的格式集合 */
  const KB_SUPPORTED_EXTS = new Set([
    'pdf', 'docx', 'pptx', 'xlsx', 'csv', 'txt', 'md',
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg',
  ])

  async function openDocByNode(node: FileTreeNode) {
    if (!node.kb_doc_id) {
      const ext = ((node._ext || node.name.split('.').pop() || '')).toLowerCase()
      if (!KB_SUPPORTED_EXTS.has(ext)) {
        window.alert(`暂不支持分析 .${ext || 'unknown'} 文件`)
        return
      }
      try {
        const doc = await apiPost<KnowledgeDocument>('/knowledge/documents', { file_id: node.id })
        mergeKnowledgeDocuments([doc])
        node.kb_doc_id = doc.id; node.kb_status = 'pending'; node._ext = doc.extension
      } catch (e) { console.error('[kb] create doc failed:', e); return }
    }
    const doc = documents.value.find(d => d.id === node.kb_doc_id)
    if (doc) openDocument(doc)
  }

  async function ensureDocument(documentId: number): Promise<KnowledgeDocument | null> {
    const existing = documents.value.find(d => d.id === documentId)
    if (existing) return existing
    try {
      const doc = await getKnowledgeDocument(documentId)
      mergeKnowledgeDocuments([doc])
      return doc
    } catch {
      return null
    }
  }

  async function handshakeLoaded() {
    const ids = documents.value.map(d => d.id)
    if (!ids.length) return
    try {
      const norm: Record<number, DocumentProgress> = { ...liveProgressMap.value }
      for (let i = 0; i < ids.length; i += PROGRESS_BATCH_SIZE) {
        const batch = ids.slice(i, i + PROGRESS_BATCH_SIZE)
        const map = await getProgressBatch(batch)
        for (const k of Object.keys(map)) norm[Number(k)] = map[k]
      }
      liveProgressMap.value = norm
      if (Object.values(norm).some(p => p.overall_status === 'running')) ensurePolling()
    } catch { /* ignore */ }
  }

  async function openDocument(doc: KnowledgeDocument) {
    const pp = pendingPageRef.value
    pendingPageRef.value = undefined
    active.value = doc; showWorkspace.value = false; showDashboard.value = false
    tab.value = pp ? 'reader' : 'overview'
    const [progressResult, statusResult] = await Promise.all([
      liveProgressMap.value[doc.id] ? Promise.resolve(liveProgressMap.value[doc.id]) : getProgress(doc.id),
      getIngestStatus(doc.id).catch(() => null),
    ])
    progress.value = progressResult
    ingestStatus.value = statusResult
    fusions.value = []; profile.value = null; relations.value = []; resultLoadErrors.value = {}; searchResults.value = []; searched.value = false
    if (progress.value.overall_status === 'running') ensurePolling()
    if (hasResult.value) await loadResult(doc.id)
    if (pp) {
      await nextTick()
      setTimeout(() => gotoPage(pp), 300)
    }
  }

  async function loadResult(docId: number) {
    const [f, pf, rel] = await Promise.allSettled([
      getFusions(docId).then(r => r.items),
      getProfile(docId),
      getRelations(docId),
    ])
    if (active.value?.id !== docId) return
    const errors: { fusions?: string; profile?: string; relations?: string } = {}
    if (f.status === 'fulfilled') fusions.value = f.value
    else { fusions.value = []; errors.fusions = '逐页内容加载失败：' + errorMessage(f.reason, '请求失败') }
    if (pf.status === 'fulfilled') profile.value = pf.value
    else { profile.value = null; errors.profile = '画像加载失败：' + errorMessage(pf.reason, '请求失败') }
    if (rel.status === 'fulfilled') relations.value = rel.value
    else { relations.value = []; errors.relations = '关联数据加载失败：' + errorMessage(rel.reason, '请求失败') }
    resultLoadErrors.value = errors
  }

  async function startAnalyze() {
    if (!active.value) return
    if (sourceUnavailable.value) {
      window.alert('原始文件不可用，无法继续分析。请重新上传或删除这条无效记录。')
      return
    }
    const isRedo = progress.value?.overall_status === 'done'
    let forceRaw = false, forceFusion = false

    if (isRedo) {
      showRedoDialog.value = true
      redoResolve = null
      const choice = await new Promise<boolean>(r => { redoResolve = r })
      showRedoDialog.value = false
      forceRaw = choice; forceFusion = choice
    }

    // 立即给用户感知：按钮灰 + 进度面板出现
    progress.value = {
      document_id: active.value.id,
      filename: active.value.filename,
      total_pages: active.value.total_pages,
      overall_status: 'running',
      overall_percent: 0,
      current_stage: '提交中',
      stages: [],
    }
    ensurePolling()

    try {
      await apiPost('/knowledge/documents/full-pipeline', {
        document_id: active.value.id,
        force_raw: forceRaw,
        force_fusion: forceFusion,
      })
      progress.value = await getProgress(active.value.id)
      ingestStatus.value = await getIngestStatus(active.value.id).catch(() => ingestStatus.value)
    } catch (error) { window.alert((error as Error).message) }
  }

  async function handleExport() {
    if (!active.value || exporting.value) return
    if (!canExport.value) {
      const reason = sourceUnavailable.value
        ? '源文件不可用，不能导出。请先恢复源文件、重新上传，或删除这条无效记录。'
        : '这份资料还没有建立可检索内容，完成分析后才能导出。'
      window.alert(reason)
      return
    }
    exporting.value = true
    try {
      const result = await exportDocument(active.value.id, exportFormat.value)
      const blob = new Blob([result.content], { type: exportFormat.value === 'html' ? 'text/html;charset=utf-8' : 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = result.filename
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      window.alert('导出失败：' + String((error as Error).message || error))
    } finally {
      exporting.value = false
    }
  }

  function guideSourceRestore() {
    platform.modules.openApp('desktop')
    window.alert('如果源文件在回收站，请在桌面文件管理器中恢复；如果源文件已丢失，请重新上传同一资料，系统会生成新的知识库记录。')
  }

  const showRedoDialog = ref(false)
  let redoResolve: ((v: boolean) => void) | null = null
  function confirmRedo(v: boolean) { if (redoResolve) redoResolve(v) }

  async function removeDocument() {
    if (!active.value) return
    if (!window.confirm('确认删除该资料及其分析结果?')) return
    await apiDelete(`/knowledge/documents/${active.value.id}`)
    active.value = null; progress.value = null
    await loadFileTree()
  }

  function ensurePolling() { if (pollTimer !== null) return; pollTimer = window.setInterval(pollTick, 1500) }
  function stopPolling() { if (pollTimer !== null) { window.clearInterval(pollTimer); pollTimer = null } }
  async function pollTick() {
    // 轮询所有非终态文档（pending / running / 缺记录的），不只已知 running 的
    const seen = new Set<number>()
    const ids: number[] = []
    for (const d of documents.value) {
      const lp = liveProgressMap.value[d.id]
      if (!lp || lp.overall_status === 'running' || lp.overall_status === 'pending') {
        ids.push(d.id)
        seen.add(d.id)
      }
    }
    // 确保当前打开的文件也在轮询中
    if (active.value && !seen.has(active.value.id)) {
      ids.push(active.value.id)
    }
    if (!ids.length) { stopPolling(); return }
    try {
      const map = await getProgressBatch(ids)
      for (const k of Object.keys(map)) liveProgressMap.value[Number(k)] = map[k]
      if (active.value) {
        const cur = map[String(active.value.id)]
        if (cur) {
          const wasRunning = progress.value?.overall_status === 'running'
          progress.value = cur
          ingestStatus.value = await getIngestStatus(active.value.id).catch(() => ingestStatus.value)
          if (wasRunning && cur.overall_status === 'done') await loadResult(active.value.id)
        }
      }
      if (!Object.values(map).some(p => p.overall_status === 'running')) stopPolling()
    } catch { /* ignore */ }
  }

  async function runSearch() {
    if (!query.value.trim()) return; searching.value = true
    searchMetadataText.value = ''
    try {
      const data = await apiPost<{ results: SearchResult[] }>('/knowledge/search', { query: query.value, top_k: 10 })
      searchResults.value = data.results; searched.value = true
    } finally { searching.value = false }
  }

  const pageRefs = ref<Record<number, HTMLElement>>({})
  function setPageRef(page: number, el: unknown) { if (el) pageRefs.value[page] = el as HTMLElement }
  async function gotoPage(page?: number) { if (!page) return; tab.value = 'reader'; await nextTick(); pageRefs.value[page]?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  async function jumpDoc(docId: number) { const doc = await ensureDocument(docId); if (doc) openDocument(doc) }

  function askAI() {
    const ctx: Record<string, unknown> = {}
    if (active.value) {
      ctx.documentId = active.value.id; ctx.documentName = active.value.filename
      ctx.searchReady = ingestStatus.value?.search_ready ?? false
      ctx.deepReady = ingestStatus.value?.deep_ready ?? false
      ctx.sourceAvailable = ingestStatus.value?.source_available ?? true
      ctx.question = '请帮我分析这份资料的内容'
    }
    platform.modules.openApp('agent', { prefill: ctx })
  }

  onMounted(async () => {
    await initRuntime('knowledge')
    await Promise.all([loadFileTree(), loadUserRole()])
    await applyOpenPayload()
  })
  onUnmounted(stopPolling)

  watch(
    () => [props.documentId, props.view, props.showGovernance] as const,
    () => { void applyOpenPayload() },
  )

  return {
    documents,
    active,
    showWorkspace,
    showDashboard,
    isAdminOrEditor,
    activeId,
    keyword,
    tab,
    showGovernanceFromPayload,
    fileTree,
    treeLoading,
    treeError,
    liveProgressMap,
    visibleTree,
    toggleFolder,
    openWorkspace,
    openDashboard,
    loadUserRole,
    jumpToFirstRunning,
	    progress,
	    ingestStatus,
    fusions,
    profile,
    relations,
    resultLoadErrors,
    query,
    searching,
    searched,
    searchResults,
    searchMetadataText,
    exportFormat,
    exporting,
    analyzing,
    analyzeButtonText,
    runningCount,
    hasResult,
    showProgress,
	    headStatusText,
	    progressHeadline,
	    progressHint,
    ringStyle,
    overallPercent,
    sourceUnavailable,
    canExport,
    graphSemanticText,
    ingestStatusLabel,
    statusClassForIngest,
    ingestStatusHint,
    profileEntities,
    profileChapters,
    profileBusinessTags,
    fileIcon,
    docName,
    statusDotClass,
    stageLabel,
    readableFailure,
    stepCount,
    confClass,
    relPct,
    analyzedDocCount,
    failedDocumentCount,
    pendingDocumentCount,
    recentDocuments,
    documentStatus,
    documentStatusText,
    highlightText,
    openSearchSource,
    downloadSearchSource,
    copySearchReference,
    showSearchMetadata,
    jumpToSearchResult,
    loadFileTree,
    applyOpenPayload,
    openDocByNode,
    openDocument,
    startAnalyze,
    handleExport,
    guideSourceRestore,
    showRedoDialog,
    confirmRedo,
    removeDocument,
    runSearch,
    setPageRef,
    gotoPage,
    jumpDoc,
    askAI,
  }
}
