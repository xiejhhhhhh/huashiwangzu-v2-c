<template>
  <div class="kb-app">
    <!-- 左侧：工作台入口 + 文件树 -->
    <aside class="kb-side">
      <button class="ws-btn" @click="openWorkspace">
        🏠 工作台
      </button>

      <input v-model="keyword" class="search-mini" placeholder="筛选文件…" />

      <div class="tree-wrap">
        <div v-if="!fileTree.length" class="empty-tip">加载中…</div>
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
      <!-- 工作台：全局知识网络 -->
      <template v-if="showWorkspace && !active">
        <div class="ws-header">
          <h2>知识网络全景</h2>
          <span class="ws-sub">系统自动织网，连线越粗关联越强</span>
        </div>
        <div v-if="graphData.nodes.length" class="graph-container" ref="graphContainer">
          <canvas ref="graphCanvas" @click="onGraphClick"></canvas>
        </div>
        <div v-else class="empty-tip pad">尚无关联数据。上传并分析多份资料后自动织网。</div>
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
            <button class="primary-btn" :disabled="analyzing" @click="startAnalyze">{{ analyzing ? '分析中…' : (progress?.overall_status === 'done' ? '重新分析' : '开始分析') }}</button>
            <button class="ghost-btn danger" @click="removeDocument">删除</button>
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

        <nav v-if="hasResult" class="tabs">
          <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">概览</button>
          <button :class="{ active: tab === 'reader' }" @click="tab = 'reader'">阅读</button>
          <button :class="{ active: tab === 'relation' }" @click="tab = 'relation'">关联</button>
          <button :class="{ active: tab === 'search' }" @click="tab = 'search'">检索</button>
        </nav>

        <section v-if="hasResult && tab === 'overview'" class="pane">
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
          <article v-for="p in fusions" :key="p.page" :ref="el => setPageRef(p.page, el)" class="page-card">
            <div class="page-head"><span class="page-no">第 {{ p.page }} 页</span><span v-if="p.page_title" class="page-title">{{ p.page_title }}</span><span class="conf" :class="confClass(p.confidence)" :title="'融合置信度'">置信 {{ Math.round((p.confidence||0)*100) }}%</span></div>
            <p class="page-text">{{ p.fused_text }}</p>
            <div v-if="p.conflicts && p.conflicts.length" class="conflict-note">⚠ 多轮识别有 {{ p.conflicts.length }} 处差异,已按多数采信</div>
          </article>
          <div v-if="!fusions.length" class="empty-tip pad">完成分析后显示逐页内容</div>
        </section>

        <section v-if="hasResult && tab === 'relation'" class="pane">
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
          <article v-for="item in searchResults" :key="item.chunk_id" class="result-card" @click="jumpDoc(item.document_id)"><div class="result-head"><span class="result-doc">{{ docName(item.document_id) }}</span><span class="result-page">第 {{ item.page||'·' }} 页</span></div><p>{{ item.text }}</p></article>
          <div v-if="searched && !searchResults.length" class="empty-tip pad">没找到相关内容</div>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import { initRuntime, platform } from '../runtime'
import {
  apiDelete, apiPost, apiGet,
  startPipeline, getProgress, getProgressBatch, getFusions, getProfile, getRelations, parseJsonField,
  getFileTree, getFileList, buildFolderTree, getRelationGraph,
  type KnowledgeDocument, type DocumentProgress, type ProgressStage,
  type FusionPage, type DocumentProfile, type FileRelation, type SearchResult,
  type FileTreeNode, type RelationGraph,
} from './api'

const documents = ref<KnowledgeDocument[]>([])
const active = ref<KnowledgeDocument | null>(null)
const showWorkspace = ref(false)
const activeId = computed(() => active.value?.id ?? null)
const keyword = ref('')
const tab = ref<'overview' | 'reader' | 'relation' | 'search'>('overview')

// ── 文件树 ──
const fileTree = ref<FileTreeNode[]>([])
const folderOpenState = ref<Record<number, boolean>>({})
const folderFiles = ref<Record<number, FileTreeNode[]>>({})  // folder_id → 文件节点列表
const kbDocMap = ref<Record<number, KnowledgeDocument>>({})
const liveProgressMap = ref<Record<number, DocumentProgress>>({})

async function toggleFolder(node: FileTreeNode) {
  const key = node.id
  const wasOpen = folderOpenState.value[key]
  folderOpenState.value[key] = !wasOpen
  // 展开时加载文件夹内文件（仅一次）
  if (!wasOpen && !folderFiles.value[key]) {
    try {
      const data = await getFileList(key)
      const children: FileTreeNode[] = (data.items || []).map((f: {id:number;name:string;extension?:string|null;is_folder:boolean}) => {
        const doc = kbDocMap.value[f.id]
        const node: FileTreeNode = {
          id: f.id, name: f.name, parent_id: key, is_folder: f.is_folder,
          children: [], _depth: 0, _open: false, _ext: f.extension || '',
          _pct: null, _created_at: (f as any).created_at || '',
        }
        if (doc) {
          node.kb_doc_id = doc.id
          const statuses = [doc.fusion_status, doc.raw_status, doc.parse_status].filter(Boolean) as string[]
          if (statuses.includes('failed')) node.kb_status = 'failed'
          else if (statuses.every(s => s === 'done')) node.kb_status = 'done'
          else if (statuses.some(s => s === 'running' || s === 'collecting' || s === 'parsing' || s === 'fusing')) node.kb_status = 'running'
          else node.kb_status = 'pending'
          const p = liveProgressMap.value[doc.id]
          if (p && p.overall_status === 'running') node._pct = p.overall_percent
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
        out.push({ ...n, _depth: depth, _open: open })
        if (open || kw) out.push(...childFlat)
      }
    }
    return out
  }
  return flatten(fileTree.value, 0)
})

// ── 全局知识网络 ──
const graphData = ref<RelationGraph>({ nodes: [], edges: [] })
const relationCount = ref(0)
const graphContainer = ref<HTMLElement | null>(null)
const graphCanvas = ref<HTMLCanvasElement | null>(null)
const layoutPositions = ref<Map<number, { x: number; y: number }>>(new Map())

async function loadGlobalGraph() {
  try {
    // 优先用实体图（节点=概念/标签），没有则回退文档关系图
    const eg = await apiGet<RelationGraph>('/knowledge/entity-graph')
    if (eg.nodes.length) {
      // 实体图：标准化字段名
      graphData.value = {
        nodes: eg.nodes,
        edges: (eg.edges || []).map((e: any) => ({
          source: e.source, target: e.target,
          relation_type: e.relation || 'related',
          similarity_score: e.weight || 0.5,
          shared_entities: e.description ? [e.description] : [],
        })),
      }
    } else {
      const g = await getRelationGraph()
      graphData.value = g
    }
    relationCount.value = graphData.value.edges.length
    if (showWorkspace.value && graphData.value.nodes.length) { await nextTick(); renderGraph() }
  } catch { /* ignore */ }
}

function openWorkspace() {
  showWorkspace.value = true
  active.value = null
  if (graphData.value.nodes.length) {
    // 等 flex 布局完成再渲染
    requestAnimationFrame(() => requestAnimationFrame(() => renderGraph()))
  }
}

function renderGraph() {
  const canvas = graphCanvas.value
  const container = graphContainer.value
  if (!canvas || !container) return
  const rect = container.getBoundingClientRect()
  const W = rect.width, H = rect.height
  if (W < 10 || H < 10) return

  const dpr = window.devicePixelRatio || 1
  canvas.width = W * dpr; canvas.height = H * dpr
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px'
  const ctx = canvas.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const { nodes, edges } = graphData.value
  if (!nodes.length) { return }

  // ═══ 背景 ═══
  ctx.fillStyle = '#030812'; ctx.fillRect(0, 0, W, H)
  ctx.strokeStyle = 'rgba(23,65,95,0.25)'; ctx.lineWidth = 0.5
  const gs = 50
  for (let x = gs; x < W; x += gs) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke() }
  for (let y = gs; y < H; y += gs) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke() }

  // ═══ 力导向布局 ═══
  const cx = W / 2, cy = H / 2
  type LNode = { id: number; label: string; x: number; y: number; vx: number; vy: number }
  const lays: LNode[] = nodes.map((n, i) => {
    const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2
    const r = Math.min(W, H) * 0.28
    return { id: n.id, label: n.label, x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r, vx: 0, vy: 0 }
  })
  const nmap = new Map<number, LNode>()
  lays.forEach(n => nmap.set(n.id, n))
  const maxSim = Math.max(1, ...edges.map(e => e.similarity_score))

  for (let iter = 0; iter < 200; iter++) {
    for (let a = 0; a < lays.length; a++) {
      for (let b = a + 1; b < lays.length; b++) {
        const dx = lays[b].x - lays[a].x, dy = lays[b].y - lays[a].y
        const d = Math.max(1, Math.hypot(dx, dy)); const f = 450 / (d * d)
        lays[a].vx -= (dx / d) * f; lays[a].vy -= (dy / d) * f
        lays[b].vx += (dx / d) * f; lays[b].vy += (dy / d) * f
      }
    }
    for (const e of edges) {
      const s = nmap.get(e.source), t = nmap.get(e.target)
      if (!s || !t) continue
      const dx = t.x - s.x, dy = t.y - s.y, d = Math.max(1, Math.hypot(dx, dy))
      const f = (d - 80) * 0.004 * (e.similarity_score / maxSim)
      s.vx += (dx / d) * f; s.vy += (dy / d) * f
      t.vx -= (dx / d) * f; t.vy -= (dy / d) * f
    }
    for (const n of lays) {
      n.vx += (cx - n.x) * 0.001; n.vy += (cy - n.y) * 0.001
      if (!isFinite(n.vx)) n.vx = 0; if (!isFinite(n.vy)) n.vy = 0
      n.vx *= 0.72; n.vy *= 0.72
      n.x += n.vx; n.y += n.vy
      n.x = Math.max(60, Math.min(W - 60, n.x)); n.y = Math.max(60, Math.min(H - 60, n.y))
    }
  }
  const posMap = new Map<number, { x: number; y: number }>()
  lays.forEach(n => posMap.set(n.id, { x: n.x, y: n.y }))
  layoutPositions.value = posMap

  // ═══ 边（双层发光：粗暗底 + 细亮线） ═══
  const edgeColors: Record<string, string> = {
    semantic_similar: '#5599cc', entity_overlap: '#66dd66',
    hierarchy: '#ffaa44', reference: '#ff7777',
    属于: '#ffaa44', 位于: '#5599cc', 产生: '#66dd66',
    包含: '#c098ff', 引用: '#ff7777', 相关: '#6699cc',
  }
  for (const e of edges) {
    const s = nmap.get(e.source), t = nmap.get(e.target)
    if (!s || !t) continue
    const w = e.similarity_score / maxSim
    const color = edgeColors[e.relation_type] || '#6699cc'
    // glow
    ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y)
    ctx.strokeStyle = color + '1a'; ctx.lineWidth = 3 + w * 10; ctx.stroke()
    // core
    ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y)
    const alpha = Math.floor(0x30 + w * 0x50).toString(16)
    ctx.strokeStyle = color + alpha; ctx.lineWidth = 0.8 + w * 2.5; ctx.stroke()
  }

  // ═══ 节点（HoloGram 色板） ═══
  const nodeColors = [0x7eb8ff, 0xf0c060, 0xc098ff, 0x8ec8ff, 0x6aadff, 0x66dd66]
  const R = 20
  for (let i = 0; i < lays.length; i++) {
    const n = lays[i]
    const hex = '#' + nodeColors[i % nodeColors.length].toString(16).padStart(6, '0')
    // glow
    const g = ctx.createRadialGradient(n.x, n.y, R * 0.2, n.x, n.y, R * 2)
    g.addColorStop(0, hex + '55'); g.addColorStop(1, 'transparent')
    ctx.beginPath(); ctx.arc(n.x, n.y, R * 2, 0, Math.PI * 2)
    ctx.fillStyle = g; ctx.fill()
    // circle
    ctx.beginPath(); ctx.arc(n.x, n.y, R, 0, Math.PI * 2)
    ctx.fillStyle = hex; ctx.fill()
    ctx.strokeStyle = 'rgba(255,255,255,0.2)'; ctx.lineWidth = 1.5; ctx.stroke()
    // label
    ctx.fillStyle = '#ccd6e0'; ctx.font = '12px 苹方,"微软雅黑",sans-serif'
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'
    ctx.fillText(n.label, n.x, n.y + R + 8)
  }
}
function onGraphClick(e: MouseEvent) {
  const canvas = graphCanvas.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  let closestId = 0, closestDist = Infinity
  for (const [id, pos] of layoutPositions.value) {
    const dist = Math.hypot(mx - pos.x, my - pos.y)
    if (dist < 40 && dist < closestDist) { closestDist = dist; closestId = id }
  }
  if (closestId) {
    const doc = documents.value.find(d => d.id === closestId)
    if (doc) openDocument(doc)
  }
}

// ── 进度/分析 ──
const progress = ref<DocumentProgress | null>(null)
const fusions = ref<FusionPage[]>([])
const profile = ref<DocumentProfile | null>(null)
const relations = ref<FileRelation[]>([])
const query = ref('')
const searching = ref(false)
const searched = ref(false)
const searchResults = ref<SearchResult[]>([])
let pollTimer: number | null = null

const analyzing = computed(() => progress.value?.overall_status === 'running')
const hasResult = computed(() => progress.value?.overall_status === 'done' || fusions.value.length > 0)
const showProgress = computed(() => !!progress.value && progress.value.overall_status !== 'done')
const headStatusText = computed(() => { const p = progress.value; if (!p) return '尚未分析'; if (p.overall_status === 'done') return '分析完成'; if (p.overall_status === 'failed') return '分析出错'; if (p.overall_status === 'running') return p.current_stage + '…'; return '待分析' })
const progressHeadline = computed(() => { const p = progress.value; if (!p) return ''; if (p.overall_status === 'done') return '全部完成'; if (p.overall_status === 'failed') return '分析出错,可重新分析'; return '正在「' + p.current_stage + '」' })
const ringStyle = computed(() => { const pct = progress.value?.overall_percent ?? 0; return { background: `conic-gradient(#2395bc ${pct * 3.6}deg, #e6eef5 0deg)` } })
const profileEntities = computed(() => parseJsonField<Array<{ name: string }>>(profile.value?.key_entities, []).slice(0, 12))
const profileChapters = computed(() => parseJsonField<Array<{ title?: string; page?: number }>>(profile.value?.chapter_structure, []))

function fileIcon(ext?: string): string { const e = (ext || '').toLowerCase(); if (e === 'pdf') return '📕'; if (['doc','docx'].includes(e)) return '📘'; if (['xls','xlsx'].includes(e)) return '📗'; if (['ppt','pptx'].includes(e)) return '📙'; if (['png','jpg','jpeg','gif','webp'].includes(e)) return '🖼'; return '📄' }
function docName(id: number): string { return documents.value.find(d => d.id === id)?.filename || ('资料 #'+id) }
function statusDotClass(status?: string): string { if (status === 'done') return 'ok'; if (status === 'running' || status === 'collecting' || status === 'parsing' || status === 'fusing') return 'busy'; return 'idle' }
function stepCount(s: ProgressStage): string { if (s.key === 'graph') return s.count ? `${s.count} 个实体` : (s.status === 'done' ? '完成' : '—'); if (s.key === 'relation') return s.count ? `${s.count} 条关联` : (s.status === 'done' ? '完成' : '—'); if (s.total <= 1) return s.status === 'done' ? '完成' : (s.status === 'running' ? '进行中' : '—'); return `${s.done}/${s.total}` }
function confClass(c?: number): string { const v = c || 0; if (v >= 0.9) return 'high'; if (v >= 0.75) return 'mid'; return 'low' }
function relPct(r: FileRelation): number { return Math.round((r.similarity_score || 0) * 100) }

async function loadFileTree() {
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
          const statuses = [doc.fusion_status, doc.raw_status, doc.parse_status]
          if (statuses.includes('failed')) n.kb_status = 'failed'
          else if (statuses.every(s => s === 'done')) n.kb_status = 'done'
          else if (statuses.some(s => s === 'running' || s === 'collecting' || s === 'parsing' || s === 'fusing')) n.kb_status = 'running'
          else n.kb_status = 'pending'
          const p = liveProgressMap.value[doc.id]
          if (p && p.overall_status === 'running') n._pct = p.overall_percent
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
          _created_at: (f as any).created_at || '',
        }
        if (doc) {
          fn.kb_doc_id = doc.id
          const statuses = [doc.fusion_status, doc.raw_status, doc.parse_status].filter(Boolean) as string[]
          if (statuses.includes('failed')) fn.kb_status = 'failed'
          else if (statuses.every(s => s === 'done')) fn.kb_status = 'done'
          else if (statuses.some(s => s === 'running' || s === 'collecting' || s === 'parsing' || s === 'fusing')) fn.kb_status = 'running'
          else fn.kb_status = 'pending'
          const p = liveProgressMap.value[doc.id]
          if (p && p.overall_status === 'running') fn._pct = p.overall_percent
        }
        rootFiles.push(fn)
      }
      rootFiles.sort((a, b) => (b._created_at || '').localeCompare(a._created_at || ''))
      if (rootFiles.length) fileTree.value = [...tree, ...rootFiles]
    } catch { /* ignore */ }
    await handshakeAll()
  } catch (e) { console.error('[kb] loadFileTree:', e) }
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
  active.value = doc; showWorkspace.value = false; tab.value = 'overview'
  progress.value = liveProgressMap.value[doc.id] || await getProgress(doc.id)
  fusions.value = []; profile.value = null; relations.value = []; searchResults.value = []; searched.value = false
  if (progress.value.overall_status === 'running') ensurePolling()
  if (hasResult.value) await loadResult(doc.id)
}

async function loadResult(docId: number) {
  const [f, pf, rel] = await Promise.all([
    getFusions(docId).then(r => r.items).catch(() => []),
    getProfile(docId).catch(() => null),
    getRelations(docId).catch(() => []),
  ])
  if (active.value?.id !== docId) return
  fusions.value = f; profile.value = pf; relations.value = rel
}

async function startAnalyze() {
  if (!active.value) return
  const isRedo = progress.value?.overall_status === 'done'
  let forceRaw = false, forceFusion = false
  if (isRedo) {
    const choice = window.confirm(
      '重新分析将重跑 LLM 分析层（画像/图谱/关联）。\n\n' +
      '是否同时重跑固化数据层（原始采集 + 融合）？\n\n' +
      '点击「确定」全部重跑，「取消」仅重跑 LLM 分析层。'
    )
    forceRaw = choice; forceFusion = choice
  }
  try {
    await apiPost('/knowledge/documents/full-pipeline', {
      document_id: active.value.id,
      force_raw: forceRaw,
      force_fusion: forceFusion,
    })
    progress.value = await getProgress(active.value.id)
    ensurePolling()
  } catch (error) { window.alert((error as Error).message) }
}

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
  const ids = documents.value.filter(d => liveProgressMap.value[d.id]?.overall_status === 'running' || d.id === active.value?.id).map(d => d.id)
  if (!ids.length) { stopPolling(); return }
  try {
    const map = await getProgressBatch(ids)
    for (const k of Object.keys(map)) liveProgressMap.value[Number(k)] = map[k]
    if (active.value) {
      const cur = map[String(active.value.id)]
      if (cur) {
        const wasRunning = progress.value?.overall_status === 'running'
        progress.value = cur
        if (wasRunning && cur.overall_status === 'done') await loadResult(active.value.id)
      }
    }
    if (!Object.values(map).some(p => p.overall_status === 'running')) stopPolling()
  } catch { /* ignore */ }
}

async function runSearch() {
  if (!query.value.trim()) return; searching.value = true
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
    ctx.question = '请帮我分析这份资料的内容'
  }
  platform.modules.openApp('agent', { prefill: ctx })
}

onMounted(async () => {
  await initRuntime('knowledge')
  await Promise.all([loadFileTree(), loadGlobalGraph()])
})
onUnmounted(stopPolling)
</script>

<style scoped>
.kb-app { display: grid; grid-template-columns: 260px minmax(0, 1fr); height: 100%; min-height: 640px; background: #f3f6fb; color: #1f2a37; font-family: 苹方,"微软雅黑",宋体,sans-serif; }

/* 左侧 */
.kb-side { display: flex; flex-direction: column; gap: 8px; padding: 12px; background: #fff; border-right: 1px solid #e3e9f2; min-width: 0; }

.ws-btn { width: 100%; padding: 10px 12px; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; cursor: pointer; font-size: 14px; font-weight: 600; color: #46586b; text-align: left; }
.ws-btn:hover { border-color: #2395bc; color: #2395bc; background: #f7fbfe; }

.search-mini { height: 34px; padding: 0 12px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #1f2a37; outline: none; }
.search-mini:focus { border-color: #2395bc; }

.tree-wrap { flex: 1; min-height: 0; overflow: auto; }
.tree-node { display: flex; align-items: center; gap: 4px; width: 100%; padding: 5px 6px; text-align: left; cursor: pointer; border: none; background: transparent; font-size: 12px; color: #46586b; border-radius: 6px; }
.tree-node:hover { background: #f0f6fb; }
.tree-node.active { background: #eaf6fb; color: #2395bc; font-weight: 600; }
.tree-arrow { font-size: 8px; width: 10px; flex: none; color: #8aa0b5; }
.tree-icon { font-size: 14px; flex: none; }
.tree-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.tree-dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.tree-dot.ok { background: #2bb673; }
.tree-dot.busy { background: #f0b240; animation: pulse 1s infinite; }
.tree-dot.idle { background: #c2cdda; }
.tree-pct { font-size: 10px; font-weight: 700; color: #f0941f; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* 主区 */
.kb-main { display: flex; flex-direction: column; min-width: 0; padding: 18px 20px; gap: 14px; overflow: hidden; height: 100%; }

.ws-header { display: flex; align-items: baseline; gap: 12px; flex: none; }
.ws-header h2 { margin: 0; font-size: 18px; color: #1c3a4a; }
.ws-sub { font-size: 12px; color: #8aa0b5; }
.graph-container { flex: 1; min-height: 200px; border: 1px solid #1a2d42; border-radius: 12px; background: #0a1628; overflow: hidden; position: relative; }
.graph-container canvas { display: block; }

.main-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid #e3e9f2; }
.head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.head-ico { font-size: 30px; }
.main-head h2 { margin: 0; font-size: 18px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head-meta { font-size: 12px; color: #7c8da0; }
.head-actions { display: flex; gap: 8px; flex: none; }

.primary-btn { height: 36px; padding: 0 18px; border: none; border-radius: 8px; cursor: pointer; background: #2395bc; color: #fff; font-weight: 600; font-size: 13px; }
.primary-btn:hover { background: #1f86a9; }
.primary-btn:disabled { background: #aebfcc; cursor: not-allowed; }
.ghost-btn { height: 36px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #46586b; cursor: pointer; }
.ghost-btn:hover { border-color: #bcd6e6; }
.ghost-btn.danger:hover { border-color: #e5534b; color: #e5534b; }

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

.tabs { display: flex; gap: 4px; border-bottom: 1px solid #e3e9f2; flex: none; }
.tabs button { height: 38px; padding: 0 18px; border: none; background: transparent; color: #5a6b7d; cursor: pointer; font-size: 14px; border-radius: 8px 8px 0 0; }
.tabs button:hover { color: #2395bc; }
.tabs button.active { color: #2395bc; font-weight: 700; box-shadow: inset 0 -2px 0 #2395bc; }

.pane { flex: 1; min-height: 0; overflow: auto; }

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
.result-head { display: flex; justify-content: space-between; font-size: 12px; color: #7c8da0; margin-bottom: 8px; }
.result-doc { font-weight: 600; color: #2395bc; }
.result-card p { margin: 0; line-height: 1.7; color: #2a3a48; }

.empty-tip { color: #9aabbd; font-size: 13px; text-align: center; padding: 14px; }
.empty-tip.pad { padding: 40px; }
</style>
