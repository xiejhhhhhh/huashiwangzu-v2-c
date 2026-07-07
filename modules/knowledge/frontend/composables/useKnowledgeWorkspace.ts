import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { authHeaders, getApiUrl, initRuntime, platform } from '../../runtime'
import {
  apiDelete,
  apiGet,
  apiPost,
  buildFolderTree,
  exportDocument,
  getFileList,
  getFileTree,
  getFusions,
  getIngestStatus,
  getProfile,
  getProgress,
  getProgressBatch,
  getRelations,
  listKnowledgeDocuments,
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
import type { GraphNode } from '../graph3d/types'
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
  const folderFiles = ref<Record<number, FileTreeNode[]>>({})  // folder_id → 文件节点列表
  const kbDocMap = ref<Record<number, KnowledgeDocument>>({})
  const liveProgressMap = ref<Record<number, DocumentProgress>>({})

  const DOCUMENT_PAGE_SIZE = 100
  const FILE_PAGE_SIZE = 200
  const PROGRESS_BATCH_SIZE = 100

  // ── 树节点状态/百分比实时派生（从 liveProgressMap 现查，不存静态快照） ──
  function getNodeLiveStatus(node: FileTreeNode): string | undefined {
    if (node.is_folder || !node.kb_doc_id) return undefined
    const lp = liveProgressMap.value[node.kb_doc_id]
    if (lp) {
      if (lp.overall_status === 'running') return 'running'
      if (lp.overall_status === 'done') return 'done'
      if (lp.overall_status === 'failed') return 'failed'
      if (lp.overall_status === 'degraded') return 'failed'
      if (lp.overall_status === 'source_unavailable') return 'failed'
      return 'pending'
    }
    // 兜底：liveProgressMap 无记录时用 doc 粗状态字段
    const doc = kbDocMap.value[node.id]
    if (!doc) return undefined
    const statuses = [doc.fusion_status, doc.raw_status, doc.parse_status].filter(Boolean) as string[]
    if (statuses.includes('failed')) return 'failed'
    if (statuses.every(s => s === 'done')) return 'done'
    if (statuses.some(s => s === 'running' || s === 'collecting' || s === 'parsing' || s === 'fusing')) return 'running'
    return 'pending'
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
    // 展开时加载文件夹内文件（仅一次）
    if (!wasOpen && !folderFiles.value[key]) {
      try {
        const items = await loadAllFilesInFolder(key)
        const children: FileTreeNode[] = items.filter((f) => !f.is_folder).map((f) => {
          const doc = kbDocMap.value[f.id]
          const node: FileTreeNode = {
            id: f.id, name: f.name, parent_id: key, is_folder: f.is_folder,
            node_key: `${f.is_folder ? 'folder' : 'file'}:${f.id}`,
            children: [], _depth: 0, _open: false, _ext: f.extension || '',
            _pct: null, _created_at: f.created_at || '',
          }
          if (doc) {
            node.kb_doc_id = doc.id
            // kb_status / _pct 由 visibleTree 透过 liveProgressMap 实时派生
          }
          return node
        })
        folderFiles.value[key] = children
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

  // ── 全局知识网络（由 WorkspaceGraph 接管） ──

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

  /** Handle node selection from 3D graph */
  function handleGraphSelect(node: GraphNode) {
    const nodeId = node.id
    // Try document lookup first (relation-graph nodes use document ids)
    const doc = documents.value.find(d => d.id === nodeId)
    if (doc) {
      openDocument(doc)
      return
    }
    // For entity-graph nodes, try by entity_id or graph node id
    // Fallback: try node.label match in document filenames
    const docByName = documents.value.find(d => d.filename.includes(node.label))
    if (docByName) {
      openDocument(docByName)
      return
    }
    // Last resort: log and ignore
    console.log('[kb] graph node selected (no document match):', nodeId, node.label)
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
  const hasResult = computed(() => progress.value?.overall_status === 'done' || fusions.value.length > 0)
  const showProgress = computed(() => !!progress.value && progress.value.overall_status !== 'done')
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
  function statusDotClass(status?: string): string { if (status === 'done') return 'ok'; if (status === 'running' || status === 'collecting' || status === 'parsing' || status === 'fusing') return 'busy'; if (status === 'failed' || status === 'source_unavailable') return 'failed'; if (status === 'paused') return 'warn'; return 'idle' }
  function stageLabel(stage: string): string { const labels: Record<string, string> = { source: '源文件', parse: '解析', vector: '索引', raw: '原始采集', fusion: '页级融合', profile: '画像', graph: '图谱', relation: '关联', complete: '完成' }; return labels[stage] || stage }
  function sourceStateText(state: string): string { const labels: Record<string, string> = { source_file_deleted: '原始文件已删除或进入回收站。', source_file_missing: '原始文件路径不可用。', permission_denied: '当前账号没有访问原始文件的权限。', source_unavailable: '原始文件不可用。' }; return labels[state] || '原始文件不可用。' }
  function readableFailure(message: string): string { return message.replace(/^Document source file unavailable:\s*/i, '源文件不可用：') }
  function errorMessage(error: unknown, fallback: string): string { return error instanceof Error && error.message ? error.message : fallback }
  function stepCount(s: ProgressStage): string { if (s.key === 'graph') return s.count ? `${s.count} 个实体` : (s.status === 'done' ? '完成' : '—'); if (s.key === 'relation') return s.count ? `${s.count} 条关联` : (s.status === 'done' ? '完成' : '—'); if (s.total <= 1) return s.status === 'done' ? '完成' : (s.status === 'running' ? '进行中' : '—'); return `${s.done}/${s.total}` }
  function confClass(c?: number): string { const v = c || 0; if (v >= 0.9) return 'high'; if (v >= 0.75) return 'mid'; return 'low' }
  function relPct(r: FileRelation): number { return Math.round((r.similarity_score || 0) * 100) }
  const analyzedDocCount = computed(() => {
    return documents.value.filter(d => {
      const lp = liveProgressMap.value[d.id]
      return lp?.overall_status === 'done' || (!lp && d.parse_status === 'done')
    }).length
  })
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
      `chunk_id=${item.chunk_id}`,
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
      explain: item.explain,
    }, null, 2)
  }
  async function jumpToSearchResult(item: SearchResult) {
    const doc = documents.value.find(d => d.id === item.document_id)
    if (!doc) return
    pendingPageRef.value = item.page ?? undefined
    await openDocument(doc)
  }

  async function loadAllKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
    const all: KnowledgeDocument[] = []
    for (let page = 1; page <= 100; page += 1) {
      const data = await listKnowledgeDocuments(page, DOCUMENT_PAGE_SIZE)
      all.push(...(data.items || []))
      if (all.length >= data.total || (data.items || []).length < DOCUMENT_PAGE_SIZE) break
    }
    return all
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

  async function loadFileTree() {
    treeLoading.value = true
    treeError.value = ''
    try {
      const [folders, docs] = await Promise.all([
        getFileTree(),
        loadAllKnowledgeDocuments(),
      ])
      documents.value = docs
      const tree = buildFolderTree(folders)
      const docByFileId: Record<number, KnowledgeDocument> = {}
      for (const d of docs) docByFileId[d.file_id] = d
      kbDocMap.value = docByFileId

      function attachDocs(nodes: FileTreeNode[]) {
        for (const n of nodes) {
          n._depth = 0; n._open = false; n._ext = ''; n._pct = null
          const doc = docByFileId[n.id]
          if (doc) {
            n.kb_doc_id = doc.id
            // kb_status / _pct 由 visibleTree 透过 liveProgressMap 实时派生
          }
          n._ext = (doc?.extension) || ''
          if (n.children.length) attachDocs(n.children)
        }
      }
      attachDocs(tree)
      // 文件夹排前，文件排后
      tree.sort((a, b) => {
        if (a.is_folder !== b.is_folder) return a.is_folder ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      fileTree.value = tree

      // 加载根目录文件（folder_id=0 的文件和文件夹混合）
      try {
        const rootItems = await loadAllFilesInFolder(0)
        const rootFiles: FileTreeNode[] = []
        for (const f of rootItems) {
          if (f.is_folder) continue  // 文件夹已在 tree 中
          const doc = kbDocMap.value[f.id]
          const fn: FileTreeNode = {
            id: f.id, name: f.name, parent_id: null, is_folder: false,
            node_key: `file:${f.id}`,
            children: [], _depth: 0, _open: false, _ext: f.extension || '', _pct: null,
            _created_at: f.created_at || '',
          }
          if (doc) {
            fn.kb_doc_id = doc.id
            // kb_status / _pct 由 visibleTree 透过 liveProgressMap 实时派生
          }
          rootFiles.push(fn)
        }
        rootFiles.sort((a, b) => (b._created_at || '').localeCompare(a._created_at || ''))
        if (rootFiles.length) fileTree.value = [...tree, ...rootFiles]
      } catch { /* ignore */ }
      await handshakeAll()

      // ── 自动登记未入库的已支持格式文件（上传即分析零点击） ──
      await autoRegisterUnregistered()
    } catch (e: unknown) {
      console.error('[kb] loadFileTree:', e)
      treeError.value = '知识库文件树加载失败：' + String((e as Error).message || e)
    } finally {
      treeLoading.value = false
    }
  }

  async function applyOpenPayload() {
    if (typeof props.documentId === 'number' && props.documentId > 0) {
      const doc = documents.value.find(d => d.id === props.documentId)
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

  /**
   * 遍历文件树,自动登记支持格式但尚未入库的文件。
   * 同时补齐已登记但未完成（raw_status≠done 或 fusion_status≠done）的文档。
   * 分批串行(Promise.allSettled),每批最多3个,避免塞爆任务队列。
   */
  async function autoRegisterUnregistered() {
    const toRegister: FileTreeNode[] = []
    function collect(nodes: FileTreeNode[]) {
      for (const n of nodes) {
        if (!n.is_folder) {
          const ext = ((n._ext || n.name.split('.').pop() || '')).toLowerCase()
          if (KB_SUPPORTED_EXTS.has(ext) && !kbDocMap.value[n.id]) {
            toRegister.push(n)
          }
        }
        if (n.children.length) collect(n.children)
      }
    }
    collect(fileTree.value)

    if (!toRegister.length) return
    console.log(`[kb] Auto-registering ${toRegister.length} supported files...`)

    // 分批,每批最多3个
    const BATCH_SIZE = 3
    for (let i = 0; i < toRegister.length; i += BATCH_SIZE) {
      const batch = toRegister.slice(i, i + BATCH_SIZE)
      const results = await Promise.allSettled(
        batch.map(n =>
          apiPost<KnowledgeDocument>('/knowledge/documents', { file_id: n.id })
            .then((doc: KnowledgeDocument) => ({ node: n, doc }))
        )
      )
      for (const r of results) {
        if (r.status === 'fulfilled') {
          const { node, doc } = r.value
          node.kb_doc_id = doc.id
          node.kb_status = 'pending'
          kbDocMap.value[node.id] = doc
          documents.value.push(doc)
          console.log(`[kb] Registered: ${node.name} → doc_id=${doc.id}`)
        } else {
          console.warn('[kb] Register failed:', r.reason)
        }
      }
      // 每批之间等一小会儿,别打太快
      if (i + BATCH_SIZE < toRegister.length) {
        await new Promise(r => setTimeout(r, 500))
      }
    }

    // 登记完握手一次进度；已登记文档由后端断点队列接管，不在前端打开时批量补跑。
    await handshakeAll()
  }

  /**
   * 补齐已登记但未完成分析（非终态、且未在运行中）的文档。
   * 幂等：正在跑的文档不重复入队。
   * 双重保护：liveProgressMap（实时进度）+ 文档自身 status 字段（持久化）。
   * 当 progress-batch 因网络/auth 问题失败时，liveProgressMap 可能为空，
   * 此时 fallback 到文档自身的 raw_status/fusion_status 判断状态，避免
   * 每次打开知识库都重新触发全部分析。
   */
  async function retryPendingDocuments() {
    const toRetry: number[] = []
    for (const d of documents.value) {
      // 文档自身持久化状态（不受 liveProgressMap 空影响）
      const rs = (d.raw_status || d.parse_status || '').toLowerCase()
      const fs = (d.fusion_status || '').toLowerCase()
      const docStatusFailed = rs === 'failed' || fs === 'failed'
      const docStatusDone = rs === 'done' || fs === 'done' || (rs === 'done' && fs === 'done')
      const docStatusRunning = rs === 'running' || rs === 'collecting' || rs === 'parsing' || fs === 'running' || fs === 'fusing'
      const docStatusPending = !rs || (!docStatusDone && !docStatusFailed && !docStatusRunning)

      // liveProgressMap 实时进度
      const lp = liveProgressMap.value[d.id]
      const lpRunning = lp?.overall_status === 'running'
      const lpFailed = lp?.overall_status === 'failed'
      const lpDegraded = lp?.overall_status === 'degraded'
      const lpUnavailable = lp?.overall_status === 'source_unavailable'
      const lpDone = lp?.overall_status === 'done'
      const lpPending = !lp || (!lpDone && !lpFailed && !lpDegraded && !lpUnavailable && !lpRunning)

      // 综合判断：两个维度都认为 pending 才 retry（防误判）
      if (!docStatusPending && !lpPending) continue
      // 任一维度认为是 running/failed/done 的不处理
      if (docStatusRunning || lpRunning || docStatusDone || lpDone || docStatusFailed || lpFailed || lpDegraded || lpUnavailable) continue

      toRetry.push(d.id)
    }
    if (!toRetry.length) return
    console.log(`[kb] Retrying ${toRetry.length} stuck documents...`)

    const BATCH_SIZE = 3
    for (let i = 0; i < toRetry.length; i += BATCH_SIZE) {
      const batch = toRetry.slice(i, i + BATCH_SIZE)
      await Promise.allSettled(
        batch.map(docId =>
          apiPost('/knowledge/documents/full-pipeline', { document_id: docId })
            .catch((e: unknown) => console.warn(`[kb] Retry failed for doc_id=${docId}:`, e))
        )
      )
      if (i + BATCH_SIZE < toRetry.length) {
        await new Promise(r => setTimeout(r, 500))
      }
    }

    // 重新握手一次
    await handshakeAll()
  }

  async function openDocByNode(node: FileTreeNode) {
    if (!node.kb_doc_id) {
      try {
        const doc = await apiPost<KnowledgeDocument>('/knowledge/documents', { file_id: node.id })
        documents.value.push(doc)
        node.kb_doc_id = doc.id; node.kb_status = 'pending'; node._ext = doc.extension
        kbDocMap.value[node.id] = doc
      } catch (e) { console.error('[kb] create doc failed:', e); return }
    }
    const doc = documents.value.find(d => d.id === node.kb_doc_id)
    if (doc) openDocument(doc)
  }

  async function handshakeAll() {
    const ids = documents.value.map(d => d.id)
    if (!ids.length) return
    try {
      const norm: Record<number, DocumentProgress> = {}
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
  async function jumpDoc(docId: number) { const doc = documents.value.find(d => d.id === docId); if (doc) openDocument(doc) }

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
    handleGraphSelect,
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
