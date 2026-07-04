<template>
  <div class="kb-app">
    <!-- 左侧：工作台入口 + 文件树 -->
    <aside class="kb-side">
      <button class="ws-btn" @click="openWorkspace">
        🏠 工作台
      </button>
      <button v-if="isAdminOrEditor" class="ws-btn" @click="openDashboard" :class="{ active: showDashboard }">
        📊 看板
      </button>

      <input v-model="keyword" class="search-mini" placeholder="筛选文件…" />

      <div v-if="runningCount > 0" class="running-hint" @click="jumpToFirstRunning">
        ⚙ {{ runningCount }} 个文件分析中…
      </div>

      <div class="tree-wrap">
        <div v-if="treeLoading" class="empty-tip">加载中…</div>
        <div v-else-if="treeError" class="tree-error" role="alert">
          <span>{{ treeError }}</span>
          <button type="button" @click="loadFileTree">重试</button>
        </div>
        <div v-else-if="!fileTree.length" class="empty-tip">暂无可分析文件</div>
        <button
          v-for="node in visibleTree"
          :key="node.id + (node.is_folder ? 'd' : 'f')"
          class="tree-node"
          :style="{ paddingLeft: (node._depth || 0) * 16 + 10 + 'px' }"
          :class="{ active: activeId && node.kb_doc_id === activeId }"
          @click="node.is_folder ? toggleFolder(node) : openDocByNode(node)"
        >
          <span class="tree-arrow" v-if="node.is_folder">{{ node._open ? '▼' : '▶' }}</span>
          <span class="tree-icon">{{ node.is_folder ? (node._open ? '📂' : '📁') : fileIcon(node._ext) }}</span>
          <span class="tree-name">{{ node.name }}</span>
          <span v-if="!node.is_folder && node.kb_status" class="tree-dot" :class="statusDotClass(node.kb_status)"></span>
          <span v-if="!node.is_folder && node._pct !== null" class="tree-pct">{{ node._pct }}%</span>
        </button>
      </div>
    </aside>

    <!-- 右侧主区 -->
    <main class="kb-main">
      <!-- 工作台：3D 深空星图 -->
      <template v-if="showWorkspace && !active">
        <WorkspaceGraph @select="handleGraphSelect" />
      </template>

      <!-- 看板 -->
      <template v-else-if="showDashboard && !active">
        <DashboardView :initial-show-governance="showGovernanceFromPayload" />
      </template>

      <!-- 无选中：欢迎 -->
      <div v-else-if="!active" class="welcome">
        <div class="welcome-card">
          <h1>知识库</h1>
          <p>从桌面拖入文件，系统会逐页做多轮交叉印证、提炼画像、构建知识网络。</p>
          <p class="welcome-sub">点击左侧「工作台」查看全局关联网络，或选择文件查看详情。</p>
        </div>
      </div>

      <!-- 选中文件：详情 -->
      <template v-else>
        <header class="main-head">
          <div class="head-left">
            <span class="head-ico">{{ fileIcon(active.extension) }}</span>
            <div>
              <h2>{{ active.filename }}</h2>
              <span class="head-meta">{{ active.total_pages || '—' }} 页 · {{ headStatusText }}</span>
            </div>
          </div>
          <div class="head-actions">
            <button class="ghost-btn" title="询问 AI" @click="askAI">🤖 问 AI</button>
            <select v-model="exportFormat" class="export-select" :disabled="!canExport || exporting">
              <option value="markdown">Markdown</option>
              <option value="html">HTML</option>
              <option value="json">JSON</option>
            </select>
            <button class="ghost-btn" :disabled="exporting" @click="handleExport">{{ exporting ? '导出中…' : '导出' }}</button>
            <button class="primary-btn" :disabled="analyzing || sourceUnavailable" @click="startAnalyze">{{ analyzing ? '分析中…' : (progress?.overall_status === 'done' ? '重新分析' : '开始分析') }}</button>
            <button class="ghost-btn danger" @click="removeDocument">删除</button>
          </div>
          <div v-if="analyzing" class="head-progress">
            <span class="hp-text">{{ progress?.current_stage || '分析中' }} · {{ overallPercent }}%</span>
            <span class="hp-bar"><span class="hp-fill" :style="{ width: overallPercent + '%' }"></span></span>
          </div>
        </header>

        <section v-if="showProgress" class="progress-panel">
          <div class="pp-top">
            <div class="pp-ring" :style="ringStyle">
              <span class="pp-ring-num">{{ progress?.overall_percent ?? 0 }}<i>%</i></span>
            </div>
            <div class="pp-top-text">
              <div class="pp-stage">{{ progressHeadline }}</div>
              <div class="pp-hint">{{ analyzing ? '正在处理,可关闭页面,稍后回来会自动接着显示进度' : '分析完成,下方查看结果' }}</div>
            </div>
          </div>
          <ol class="pp-steps">
            <li v-for="s in progress?.stages || []" :key="s.key" class="pp-step" :class="s.status">
              <span class="pp-dot"><template v-if="s.status === 'done'">✓</template><template v-else-if="s.status === 'running'">●</template><template v-else>○</template></span>
              <span class="pp-label">{{ s.label }}</span>
              <span class="pp-track"><span class="pp-fill" :style="{ width: s.percent + '%' }"></span></span>
              <span class="pp-count">{{ stepCount(s) }}</span>
            </li>
          </ol>
        </section>

        <section v-if="ingestStatus" class="status-panel" :class="{ unavailable: sourceUnavailable }">
          <div class="status-main">
            <span class="status-pill" :class="statusClassForIngest">{{ ingestStatusLabel }}</span>
            <span>{{ ingestStatusHint }}</span>
          </div>
          <div class="status-grid">
            <span>当前阶段：{{ stageLabel(ingestStatus.stage) }}</span>
            <span>可检索：{{ ingestStatus.search_ready ? '是' : '否' }}</span>
            <span>深度分析：{{ ingestStatus.deep_ready ? '已完成' : '未完成' }}</span>
            <span>可导出：{{ canExport ? '是' : '否' }}</span>
            <span>{{ graphSemanticText }}</span>
          </div>
          <div v-if="sourceUnavailable" class="status-help">
            原始文件可能已删除、在回收站、无权限或路径不可用。知识库保留了历史记录，但不能继续深度分析、检索或导出；请重新上传、重新绑定源文件，或删除这条无效记录。
            <div class="status-actions">
              <button class="ghost-btn" @click="guideSourceRestore">重新上传/恢复源文件</button>
              <button class="ghost-btn danger" @click="removeDocument">删除无效记录</button>
            </div>
          </div>
          <div v-else-if="ingestStatus.last_error" class="status-help">
            {{ readableFailure(ingestStatus.last_error) }}
          </div>
        </section>

        <nav v-if="hasResult" class="tabs">
          <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">概览</button>
          <button :class="{ active: tab === 'reader' }" @click="tab = 'reader'">阅读</button>
          <button :class="{ active: tab === 'relation' }" @click="tab = 'relation'">关联</button>
          <button :class="{ active: tab === 'search' }" @click="tab = 'search'">检索</button>
        </nav>

        <section v-if="hasResult && tab === 'overview'" class="pane">
          <div v-if="resultLoadErrors.profile" class="pane-error" role="alert">
            {{ resultLoadErrors.profile }}
          </div>
          <div v-if="profile" class="profile-grid">
            <div class="pf-card pf-main">
              <div class="pf-tag">{{ profile.doc_type || '资料' }}</div>
              <h3>{{ profile.subject || active.filename }}</h3>
              <p class="pf-summary">{{ profile.doc_summary }}</p>
              <button class="ghost-btn" style="margin-top:8px" @click="askAI">🤖 问 AI 关于此文件</button>
            </div>
            <div v-if="profile.core_conclusions" class="pf-card"><div class="pf-h">核心结论</div><p>{{ profile.core_conclusions }}</p></div>
            <div v-if="profile.applicable_scenarios" class="pf-card"><div class="pf-h">适用场景</div><p>{{ profile.applicable_scenarios }}</p></div>
            <div v-if="profileEntities.length" class="pf-card"><div class="pf-h">关键信息</div><div class="chips"><span v-for="e,i in profileEntities" :key="i" class="chip">{{ e.name }}</span></div></div>
            <div v-if="profileChapters.length" class="pf-card pf-wide"><div class="pf-h">内容结构</div><ul class="chapter-list"><li v-for="c,i in profileChapters" :key="i" @click="gotoPage(c.page)"><span class="ch-page">P{{ c.page || '·' }}</span><span class="ch-title">{{ c.title }}</span></li></ul></div>
          </div>
          <div v-else class="empty-tip pad">画像生成中或暂无,完成分析后显示</div>
        </section>

        <section v-if="hasResult && tab === 'reader'" class="pane">
          <div v-if="resultLoadErrors.fusions" class="pane-error" role="alert">
            {{ resultLoadErrors.fusions }}
          </div>
          <article v-for="p in fusions" :key="p.page" :ref="el => setPageRef(p.page, el)" class="page-card">
            <div class="page-head"><span class="page-no">第 {{ p.page }} 页</span><span v-if="p.page_title" class="page-title">{{ p.page_title }}</span><span class="conf" :class="confClass(p.confidence)" :title="'融合置信度'">置信 {{ Math.round((p.confidence||0)*100) }}%</span></div>
            <p class="page-text">{{ p.fused_text }}</p>
            <div v-if="p.conflicts && p.conflicts.length" class="conflict-note">⚠ 多轮识别有 {{ p.conflicts.length }} 处差异,已按多数采信</div>
          </article>
          <div v-if="!fusions.length" class="empty-tip pad">完成分析后显示逐页内容</div>
        </section>

        <section v-if="hasResult && tab === 'relation'" class="pane">
          <div v-if="resultLoadErrors.relations" class="pane-error" role="alert">
            {{ resultLoadErrors.relations }}
          </div>
          <div v-if="relations.length" class="rel-list">
            <div class="rel-hint">这份资料与库中其它资料的关联(系统自动织网):</div>
            <button v-for="r in relations" :key="r.target_document_id" class="rel-card" @click="jumpDoc(r.target_document_id)">
              <span class="rel-name">{{ r.target_filename || ('资料 #'+r.target_document_id) }}</span>
              <span class="rel-bar"><span :style="{ width: relPct(r)+'%' }"></span></span>
              <span class="rel-score">{{ relPct(r) }}% 相关</span>
            </button>
          </div>
          <div v-else class="empty-tip pad">暂无关联。库里有相关资料时会自动建立联系。</div>
        </section>

        <section v-if="hasResult && tab === 'search'" class="pane">
          <div class="search-bar"><input v-model="query" class="search-input" placeholder="搜索全库知识内容…" @keyup.enter="runSearch" /><button class="primary-btn" :disabled="searching" @click="runSearch">{{ searching?'搜索中':'搜索' }}</button></div>
          <div v-if="searched" class="search-hint">在 {{ analyzedDocCount }} 个已分析文件中检索「{{ query }}」</div>
          <article v-for="item in searchResults" :key="item.chunk_id" class="result-card" @click="jumpToSearchResult(item)">
            <div class="result-head">
              <span class="result-doc">{{ item.document_name || docName(item.document_id) }}</span>
              <span class="result-page">第 {{ item.page||'·' }} 页</span>
            </div>
            <div class="result-meta">
              <span>{{ item.source_file || item.document_name || ('文档 #' + item.document_id) }}</span>
              <span v-if="item.paragraph !== null && item.paragraph !== undefined">段落 {{ item.paragraph }}</span>
              <span>{{ item.retrieval_source || 'hybrid' }} · {{ item.explain?.rrf_score ?? item.rrf_score ?? item.score }}</span>
            </div>
            <div class="result-actions">
              <button type="button" :disabled="!item.source_file_id" @click.stop="openSearchSource(item)">打开</button>
              <button type="button" :disabled="!item.source_file_id" @click.stop="downloadSearchSource(item)">下载</button>
              <button type="button" @click.stop="copySearchReference(item)">复制引用</button>
              <button type="button" @click.stop="showSearchMetadata(item)">metadata</button>
            </div>
            <p v-html="highlightText(item.text, query)"></p>
          </article>
          <pre v-if="searchMetadataText" class="result-metadata">{{ searchMetadataText }}</pre>
          <div v-if="searched && !searchResults.length" class="empty-tip pad">没找到相关内容</div>
        </section>
      </template>
    </main>

    <!-- 重新分析确认弹窗 -->
    <div v-if="showRedoDialog" class="redo-overlay" @click.self="showRedoDialog = false">
      <div class="redo-dialog">
        <div class="redo-head">
          <p class="redo-title">重新分析</p>
          <button class="redo-close" @click="confirmRedo(false)">✕</button>
        </div>
        <p class="redo-body">将重跑 LLM 分析层（画像 / 图谱 / 关联）。<br/>是否同时重跑固化数据层（原始采集 + 融合）？</p>
        <div class="redo-actions">
          <button class="redo-force" @click="confirmRedo(true)">重跑</button>
          <button class="redo-skip" @click="confirmRedo(false)">跳过</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, nextTick, watch } from 'vue'
import { initRuntime, platform, getApiUrl, authHeaders } from '../runtime'
import WorkspaceGraph from './views/WorkspaceGraph.vue'
import DashboardView from './views/DashboardView.vue'
import {
  apiDelete, apiPost, apiGet,
  startPipeline, getProgress, getIngestStatus, getProgressBatch, getFusions, getProfile, getRelations,
  exportDocument, parseJsonField,
  getFileTree, getFileList, buildFolderTree,
  type KnowledgeDocument, type DocumentProgress, type ProgressStage,
  type FusionPage, type DocumentProfile, type FileRelation, type SearchResult,
  type FileTreeNode, type KnowledgeIngestStatus, type ExportFormat,
} from './api'
import type { GraphNode } from './graph3d/types'

const props = defineProps<{
  documentId?: number
  view?: string
  showGovernance?: boolean
}>()

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
      const data = await getFileList(key)
      const children: FileTreeNode[] = (data.items || []).map((f) => {
        const doc = kbDocMap.value[f.id]
        const node: FileTreeNode = {
          id: f.id, name: f.name, parent_id: key, is_folder: f.is_folder,
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
  function flatten(nodes: FileTreeNode[], depth: number): FileTreeNode[] {
    const out: FileTreeNode[] = []
    for (const n of nodes) {
      const nameMatch = !kw || n.name.toLowerCase().includes(kw)
      // 合并子文件夹和已加载的文件，文件夹在前
      const fileKids = folderFiles.value[n.id] || []
      const allKids = [...n.children, ...fileKids].sort((a, b) => {
        if (a.is_folder !== b.is_folder) return a.is_folder ? -1 : 1
        if (!a.is_folder) return (b._created_at || '').localeCompare(a._created_at || '')
        return a.name.localeCompare(b.name)
      })
      const childFlat = allKids.length ? flatten(allKids, depth + 1) : []
      const childMatch = childFlat.length > 0
      if (nameMatch || childMatch) {
        const open = kw ? true : !!folderOpenState.value[n.id]
        out.push({ ...n, _depth: depth, _open: open,
          kb_status: getNodeLiveStatus(n),
          _pct: getNodeLivePct(n),
        })
        if (open || kw) out.push(...childFlat)
      }
    }
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
const headStatusText = computed(() => { const p = progress.value; if (!p) return '尚未分析'; if (p.overall_status === 'done') return '分析完成'; if (p.overall_status === 'failed') return '分析出错'; if (p.overall_status === 'degraded') return '分析有缺损'; if (p.overall_status === 'source_unavailable') return '源文件不可用'; if (p.overall_status === 'running') return p.current_stage + '…'; return '待分析' })
const progressHeadline = computed(() => { const p = progress.value; if (!p) return ''; if (p.overall_status === 'done') return '全部完成'; if (p.overall_status === 'failed') return '分析出错,可重新分析'; if (p.overall_status === 'degraded') return '分析有缺损,可重新分析'; if (p.overall_status === 'source_unavailable') return '源文件已删除或不可用'; return '正在「' + p.current_stage + '」' })
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
  if (status === 'running') return '处理中'
  if (status === 'queued') return '等待中'
  return '待分析'
})
const statusClassForIngest = computed(() => {
  const status = ingestStatus.value?.pipeline_status || progress.value?.overall_status || 'pending'
  if (status === 'source_unavailable' || status === 'failed') return 'err'
  if (status === 'degraded') return 'warn'
  if (status === 'running' || status === 'queued') return 'busy'
  if (status === 'deep_ready' || status === 'search_ready') return 'ok'
  return ''
})
const ingestStatusHint = computed(() => {
  const status = ingestStatus.value
  if (!status) return ''
  if (!status.source_available) return sourceStateText(status.source_state)
  if (status.next_action === 'ready') return '可以搜索、问 AI 或导出资料内容。'
  if (status.next_action === 'wait_for_search_index') return '正在建立检索索引，请稍后再试。'
  if (status.next_action === 'wait_for_deep_analysis') return '检索已可用，深度分析仍在继续。'
  if (status.next_action.includes('retry')) return '可以查看失败原因后重新分析。'
  return '可以继续分析，让资料进入可检索状态。'
})
const profileEntities = computed(() => parseJsonField<Array<{ name: string }>>(profile.value?.key_entities, []).slice(0, 12))
const profileChapters = computed(() => parseJsonField<Array<{ title?: string; page?: number }>>(profile.value?.chapter_structure, []))

function fileIcon(ext?: string): string { const e = (ext || '').toLowerCase(); if (e === 'pdf') return '📕'; if (['doc','docx'].includes(e)) return '📘'; if (['xls','xlsx'].includes(e)) return '📗'; if (['ppt','pptx'].includes(e)) return '📙'; if (['png','jpg','jpeg','gif','webp'].includes(e)) return '🖼'; return '📄' }
function docName(id: number): string { return documents.value.find(d => d.id === id)?.filename || ('资料 #'+id) }
function statusDotClass(status?: string): string { if (status === 'done') return 'ok'; if (status === 'running' || status === 'collecting' || status === 'parsing' || status === 'fusing') return 'busy'; if (status === 'failed' || status === 'source_unavailable') return 'failed'; return 'idle' }
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

async function loadFileTree() {
  treeLoading.value = true
  treeError.value = ''
  try {
    const [folders, docs] = await Promise.all([
      getFileTree(),
      apiGet<{ items: KnowledgeDocument[] }>('/knowledge/documents?page=1&page_size=100'),
    ])
    documents.value = docs.items
    const tree = buildFolderTree(folders)
    const docByFileId: Record<number, KnowledgeDocument> = {}
    for (const d of docs.items) docByFileId[d.file_id] = d
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
      const rootData = await getFileList(0)
      const rootFiles: FileTreeNode[] = []
      for (const f of (rootData.items || [])) {
        if (f.is_folder) continue  // 文件夹已在 tree 中
        const doc = kbDocMap.value[f.id]
        const fn: FileTreeNode = {
          id: f.id, name: f.name, parent_id: null, is_folder: false,
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

  // 登记完握手一次进度
  await handshakeAll()

  // ── 补齐已登记但未完成的文档（已登记但 raw_status/fusion_status 仍非终态，且未在运行中） ──
  // 用 liveProgressMap 判定状态，避免重复入队正在跑的
  await retryPendingDocuments()
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
    const map = await getProgressBatch(ids)
    const norm: Record<number, DocumentProgress> = {}
    for (const k of Object.keys(map)) norm[Number(k)] = map[k]
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
</script>

<style scoped>
.kb-app { display: grid; grid-template-columns: 260px minmax(0, 1fr); height: 100%; min-height: 640px; background: #f3f6fb; color: #1f2a37; font-family: 苹方,"微软雅黑",宋体,sans-serif; }

/* 左侧 */
.kb-side { display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #fff; border-right: 1px solid #e3e9f2; min-width: 0; }

.ws-btn { width: 100%; padding: 10px 12px; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; cursor: pointer; font-size: 14px; font-weight: 600; color: #46586b; text-align: left; }
.ws-btn:hover { border-color: #2395bc; color: #2395bc; background: #f7fbfe; }
.ws-btn.active { border-color: #2395bc; color: #2395bc; background: #eaf6fb; font-weight: 700; }

.search-mini { height: 34px; padding: 0 12px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #1f2a37; outline: none; }
.search-mini:focus { border-color: #2395bc; }

.running-hint { padding: 8px 10px; margin: 0; border-radius: 8px; background: #fef7e0; border: 1px solid #f0d78c; color: #8b6914; font-size: 12px; font-weight: 600; cursor: pointer; text-align: center; user-select: none; }
.running-hint:hover { background: #fdf0c8; border-color: #e0b84c; }

.tree-wrap { flex: 1; min-height: 0; overflow: auto; }
.tree-error {
  margin: 6px 0;
  padding: 10px;
  border: 1px solid #f1b6ae;
  border-radius: 8px;
  background: #fff7f6;
  color: #b42318;
  display: grid;
  gap: 8px;
  font-size: 12px;
}
.tree-error button {
  justify-self: start;
  height: 28px;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: #fff;
  color: inherit;
  cursor: pointer;
}
.tree-node { display: flex; align-items: center; gap: 4px; width: 100%; padding: 5px 6px; text-align: left; cursor: pointer; border: none; background: transparent; font-size: 12px; color: #46586b; border-radius: 6px; }
.tree-node:hover { background: #f0f6fb; }
.tree-node.active { background: #eaf6fb; color: #2395bc; font-weight: 600; }
.tree-arrow { font-size: 8px; width: 10px; flex: none; color: #8aa0b5; }
.tree-icon { font-size: 14px; flex: none; }
.tree-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.tree-dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.tree-dot.ok { background: #2bb673; }
.tree-dot.busy { background: #f0b240; animation: pulse 1s infinite; }
.tree-dot.failed { background: #e5534b; }
.tree-dot.idle { background: #c2cdda; }
.tree-pct { font-size: 10px; font-weight: 700; color: #f0941f; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* 主区 */
.kb-main { display: flex; flex-direction: column; min-width: 0; padding: 18px 20px; gap: 14px; overflow: hidden; height: 100%; }

.main-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 6px 16px; padding-bottom: 12px; border-bottom: 1px solid #e3e9f2; position: relative; }
.head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.head-ico { font-size: 30px; }
.main-head h2 { margin: 0; font-size: 18px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head-meta { font-size: 12px; color: #7c8da0; }
.head-actions { display: flex; gap: 8px; flex: none; }

.head-progress { width: 100%; display: flex; align-items: center; gap: 10px; padding: 4px 0 0; }
.hp-text { font-size: 11px; color: #2395bc; font-weight: 600; white-space: nowrap; flex: none; }
.hp-bar { flex: 1; height: 4px; border-radius: 2px; background: #e6eef5; overflow: hidden; }
.hp-fill { display: block; height: 100%; background: linear-gradient(90deg, #2395bc, #31a1c6); border-radius: 2px; transition: width .4s ease; }

.primary-btn { height: 36px; padding: 0 18px; border: none; border-radius: 8px; cursor: pointer; background: #2395bc; color: #fff; font-weight: 600; font-size: 13px; }
.primary-btn:hover { background: #1f86a9; }
.primary-btn:disabled { background: #aebfcc; cursor: not-allowed; }
.ghost-btn { height: 36px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #46586b; cursor: pointer; }
.ghost-btn:hover { border-color: #bcd6e6; }
.ghost-btn:disabled { color: #aab8c6; background: #f5f7fa; cursor: not-allowed; }
.ghost-btn.danger:hover { border-color: #e5534b; color: #e5534b; }
.export-select { height: 36px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #46586b; padding: 0 8px; outline: none; }
.export-select:disabled { color: #aab8c6; background: #f5f7fa; }

.progress-panel { border: 1px solid #e3e9f2; border-radius: 14px; background: #fff; padding: 20px; box-shadow: 0 2px 10px rgba(35,149,188,.05); }
.pp-top { display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
.pp-ring { width: 76px; height: 76px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; position: relative; }
.pp-ring::before { content: ''; position: absolute; width: 56px; height: 56px; border-radius: 50%; background: #fff; }
.pp-ring-num { position: relative; font-size: 20px; font-weight: 800; color: #1c3a4a; }
.pp-ring-num i { font-size: 12px; font-style: normal; color: #7c8da0; }
.pp-stage { font-size: 16px; font-weight: 700; color: #1c3a4a; }
.pp-hint { font-size: 12px; color: #8aa0b5; margin-top: 4px; }
.pp-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.pp-step { display: grid; grid-template-columns: 22px 80px 1fr 70px; align-items: center; gap: 10px; }
.pp-dot { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; background: #eef2f7; color: #aab8c6; }
.pp-step.done .pp-dot { background: #2bb673; color: #fff; }
.pp-step.running .pp-dot { background: #2395bc; color: #fff; animation: pulse 1s infinite; }
.pp-label { font-size: 13px; color: #46586b; }
.pp-step.pending .pp-label { color: #aab8c6; }
.pp-track { height: 8px; border-radius: 4px; background: #eef2f7; overflow: hidden; }
.pp-fill { display: block; height: 100%; background: linear-gradient(90deg,#2395bc,#31a1c6); border-radius: 4px; transition: width .4s ease; }
.pp-step.done .pp-fill { background: #2bb673; }
.pp-count { font-size: 12px; font-weight: 600; color: #5a6b7d; text-align: right; }

.status-panel { border: 1px solid #d5dfeb; border-radius: 12px; background: #fff; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.status-panel.unavailable { border-color: #f1b6ae; background: #fff7f6; }
.status-main { display: flex; align-items: center; gap: 10px; color: #46586b; font-size: 13px; }
.status-pill { flex: none; padding: 3px 10px; border-radius: 999px; background: #eef2f7; color: #5a6b7d; font-size: 12px; font-weight: 800; }
.status-pill.ok { background: #e3f6ec; color: #1f9d5b; }
.status-pill.busy { background: #fdf2dd; color: #c5851a; }
.status-pill.warn { background: #fff0d9; color: #b45309; }
.status-pill.err { background: #fbe9e7; color: #d4544b; }
.status-grid { display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: 12px; color: #7c8da0; }
.status-help { font-size: 12px; line-height: 1.65; color: #8a4b11; }
.status-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }

.tabs { display: flex; gap: 4px; border-bottom: 1px solid #e3e9f2; flex: none; }
.tabs button { height: 38px; padding: 0 18px; border: none; background: transparent; color: #5a6b7d; cursor: pointer; font-size: 14px; border-radius: 8px 8px 0 0; }
.tabs button:hover { color: #2395bc; }
.tabs button.active { color: #2395bc; font-weight: 700; box-shadow: inset 0 -2px 0 #2395bc; }

.pane { flex: 1; min-height: 0; overflow: auto; }
.pane-error {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #f1b6ae;
  border-radius: 8px;
  background: #fff7f6;
  color: #b42318;
  font-size: 13px;
}

.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.pf-card { border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; padding: 16px; }
.pf-main { grid-column: 1 / -1; background: linear-gradient(135deg,#f0f9fd,#eaf6fb); border-color: #cfe7f1; }
.pf-wide { grid-column: 1 / -1; }
.pf-tag { display: inline-block; padding: 2px 10px; border-radius: 20px; background: #2395bc; color: #fff; font-size: 12px; margin-bottom: 8px; }
.pf-main h3 { margin: 0 0 8px; font-size: 18px; color: #1c3a4a; }
.pf-summary { margin: 0; line-height: 1.75; color: #46586b; }
.pf-h { font-size: 13px; font-weight: 700; color: #2395bc; margin-bottom: 8px; }
.pf-card p { margin: 0; line-height: 1.7; color: #46586b; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 4px 10px; border-radius: 16px; background: #eef5f9; color: #2c6177; font-size: 12px; }
.chapter-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.chapter-list li { display: flex; gap: 10px; padding: 7px 8px; border-radius: 8px; cursor: pointer; }
.chapter-list li:hover { background: #f0f9fd; }
.ch-page { color: #2395bc; font-weight: 700; font-size: 12px; flex: none; width: 36px; }
.ch-title { color: #46586b; font-size: 13px; }

.page-card { border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; padding: 16px; margin-bottom: 12px; }
.page-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.page-no { font-weight: 700; color: #1c3a4a; }
.page-title { color: #5a6b7d; font-size: 13px; flex: 1; }
.conf { font-size: 12px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
.conf.high { background: #e3f6ec; color: #1f9d5b; }
.conf.mid { background: #fdf2dd; color: #c5851a; }
.conf.low { background: #fbe9e7; color: #d4544b; }
.page-text { margin: 0; line-height: 1.8; color: #2a3a48; white-space: pre-wrap; }
.conflict-note { margin-top: 10px; padding: 6px 10px; border-radius: 8px; background: #fdf6e8; color: #b07d18; font-size: 12px; }

.rel-hint { font-size: 13px; color: #5a6b7d; margin-bottom: 12px; }
.rel-list { display: flex; flex-direction: column; gap: 10px; }
.rel-card { display: grid; grid-template-columns: 1fr 160px 80px; align-items: center; gap: 12px; width: 100%; padding: 12px 14px; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; cursor: pointer; text-align: left; }
.rel-card:hover { border-color: #2395bc; background: #f7fbfe; }
.rel-name { font-weight: 600; color: #1c3a4a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rel-bar { height: 8px; border-radius: 4px; background: #eef2f7; overflow: hidden; }
.rel-bar span { display: block; height: 100%; background: linear-gradient(90deg,#2395bc,#31a1c6); }
.rel-score { font-size: 12px; font-weight: 700; color: #2395bc; text-align: right; }

.search-bar { display: flex; gap: 8px; margin-bottom: 14px; }
.search-input { flex: 1; height: 38px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; outline: none; }
.search-input:focus { border-color: #2395bc; }
.result-card { border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; padding: 14px; margin-bottom: 10px; cursor: pointer; }
.result-card:hover { border-color: #2395bc; }
.result-head { display: flex; justify-content: space-between; font-size: 12px; color: #7c8da0; margin-bottom: 8px; gap: 10px; }
.result-doc { font-weight: 600; color: #2395bc; }
.result-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; color: #6b7b8c; font-size: 11px; }
.result-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.result-actions button { height: 24px; padding: 0 8px; border: 1px solid #c8d6e3; border-radius: 6px; background: #fff; color: #365468; font-size: 11px; cursor: pointer; }
.result-actions button:disabled { cursor: default; opacity: 0.45; }
.result-card p { margin: 0; line-height: 1.7; color: #2a3a48; }
.result-metadata { max-height: 220px; overflow: auto; margin: 0 0 10px; padding: 10px; border: 1px solid #d8e5ee; border-radius: 8px; background: #f7fafc; color: #2a3a48; font-size: 11px; white-space: pre-wrap; }
.kw-highlight { background: #fef3c7; color: #92400e; padding: 0 2px; border-radius: 2px; }
.search-hint { font-size: 12px; color: #8aa0b5; margin-bottom: 12px; }

.empty-tip { color: #9aabbd; font-size: 13px; text-align: center; padding: 14px; }
.empty-tip.pad { padding: 40px; }

/* 重新分析弹窗 */
.redo-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.25); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.redo-dialog { background: #fff; border-radius: 14px; padding: 28px 32px; min-width: 360px; max-width: 420px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.redo-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.redo-title { margin: 0; font-size: 17px; font-weight: 700; color: #1c3a4a; }
.redo-close { border: none; background: none; cursor: pointer; font-size: 16px; color: #8aa0b5; padding: 2px 4px; border-radius: 4px; }
.redo-close:hover { color: #46586b; background: #f0f2f5; }
.redo-body { margin: 0 0 24px; font-size: 14px; color: #5a6b7d; line-height: 1.7; }
.redo-actions { display: flex; gap: 10px; justify-content: flex-end; }
.redo-skip { height: 36px; padding: 0 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; background: #2bb673; color: #fff; }
.redo-skip:hover { background: #239a5d; }
.redo-force { height: 36px; padding: 0 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; background: #e5534b; color: #fff; }
.redo-force:hover { background: #c94039; }
</style>
