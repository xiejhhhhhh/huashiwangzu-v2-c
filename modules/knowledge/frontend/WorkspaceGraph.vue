<template>
  <div class="workspace-graph" ref="containerRef">
    <!-- Three.js canvas -->
    <canvas ref="canvasRef" class="graph-canvas"></canvas>

    <!-- HUD overlay layer -->
    <div class="hud-overlay" v-if="engineReady">
      <!-- Corner brackets -->
      <div class="corner-brackets">
        <div class="cb cb-tl"><span></span><span></span></div>
        <div class="cb cb-tr"><span></span><span></span></div>
        <div class="cb cb-bl"><span></span><span></span></div>
        <div class="cb cb-br"><span></span><span></span></div>
      </div>

      <!-- Top-left title + search -->
      <div class="hud-title">
        <h1>知识网络全景</h1>
        <span class="hud-subtitle">KNOWLEDGE CONSTELLATION</span>
        <div class="search-box">
          <input
            ref="searchInput"
            v-model="searchQuery"
            type="text"
            placeholder="搜索实体…"
            class="search-input"
            @input="onSearch"
            @keydown.escape="clearSearch"
          />
          <button v-if="searchQuery" class="search-clear" @click="clearSearch">✕</button>
        </div>
      </div>

      <!-- Top-right stats + controls -->
      <div class="hud-stats">
        <span class="stat-nodes">{{ nodeCount }} 节点</span>
        <span class="stat-divider">·</span>
        <span class="stat-edges">{{ edgeCount }} 关联</span>
        <span v-if="filterType" class="stat-filter">· 筛选: {{ filterType }}</span>
      </div>

      <!-- View controls -->
      <div class="hud-controls">
        <button class="ctrl-btn" title="重置视角" @click="resetView">⟲</button>
        <button class="ctrl-btn" title="适配全部" @click="fitToView">⊡</button>
      </div>

      <!-- Bottom-right legend panel (clickable) -->
      <div class="hud-legend">
        <div class="legend-header">节点类型</div>
        <div
          class="legend-item"
          v-for="item in legendItems"
          :key="item.type"
          :class="{ active: filterType === item.type, muted: filterType && filterType !== item.type }"
          @click="toggleFilter(item.type)"
        >
          <span class="legend-dot" :style="{ background: item.color }"></span>
          <span class="legend-label">{{ item.label }}</span>
          <span class="legend-count">{{ item.count }}</span>
        </div>
      </div>

      <!-- Bottom-left tooltip -->
      <div class="hud-tooltip" v-if="tooltipNode">
        <div class="tt-name">{{ tooltipNode.label }}</div>
        <div class="tt-meta">{{ tooltipTypeLabel }} · {{ tooltipEdgeCount }} 关联</div>
      </div>
      <!-- Edge relation tooltip -->
      <div class="hud-edgetip" v-if="hoveredEdgeRelation">
        <span class="et-arrow">→</span>
        <span class="et-relation">{{ hoveredEdgeRelation.relation }}</span>
      </div>

      <!-- Search result indicator -->
      <div class="search-results" v-if="searchResults.length > 0">
        <div class="sr-header">找到 {{ searchResults.length }} 个匹配</div>
        <div
          class="sr-item"
          v-for="sr in searchResults.slice(0, 8)"
          :key="sr.node.id"
          @click="focusNode(sr.node)"
        >
          <span class="sr-dot" :style="{ background: sr.color }"></span>
          <span class="sr-label">{{ sr.node.label }}</span>
          <span class="sr-type">{{ sr.typeLabel }}</span>
        </div>
      </div>
    </div>

    <!-- Scanline overlay -->
    <div class="scanline-overlay" v-if="engineReady"></div>
    <!-- Vignette -->
    <div class="vignette-overlay" v-if="engineReady"></div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <span>星图加载中…</span>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && nodeCount === 0" class="empty-overlay">
      <span class="empty-icon">✦</span>
      <span>尚无关联数据。上传并分析多份资料后自动织网。</span>
    </div>

    <!-- Detail sidebar -->
    <transition name="slide">
      <div class="detail-panel" v-if="selectedNode">
        <div class="dp-header">
          <h3>{{ selectedNode.label }}</h3>
          <button class="dp-close" @click="closeDetail">✕</button>
        </div>
        <div class="dp-body">
          <div class="dp-field">
            <span class="dp-label">类型</span>
            <span class="dp-value">{{ getTypeDisplay(selectedNode.type) }}</span>
          </div>
          <div class="dp-field">
            <span class="dp-label">关联数</span>
            <span class="dp-value">{{ selectedNodeDegree }} 条关联</span>
          </div>
          <div class="dp-section">
            <div class="dp-section-title">关联实体</div>
            <div
              class="dp-rel-item"
              v-for="rel in relatedNodes"
              :key="rel.node.id"
              @click="focusNode(rel.node)"
            >
              <span class="rel-dot" :style="{ background: rel.color }"></span>
              <span class="rel-label">
                <span class="rel-name">{{ rel.node.label }}</span>
                <span class="rel-type">({{ getTypeDisplay(rel.node.type) }})</span>
              </span>
              <span class="rel-edge-type" v-if="rel.relation">{{ rel.relation }}</span>
            </div>
            <div v-if="relatedNodes.length === 0" class="dp-empty">无关联</div>
          </div>
          <div class="dp-actions">
            <button class="dp-ai-btn" @click="askAI(selectedNode)">
              🤖 问 AI
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { GraphEngine } from './graph3d/GraphEngine'
import { computeLayout } from './graph3d/layout3d'
import { theme, resolveNodeColor, getNodeColor, getNodeRadius, nodeTypeVisualMap, typeDisplayLabels, mapChineseCategory } from './graph3d/theme'
import { NodeType, type GraphNode, type GraphEdge } from './graph3d/types'
import { getApiUrl } from '../runtime'

const emit = defineEmits<{
  select: [node: GraphNode]
}>()

// ── Engine refs ──
const containerRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const engine = ref<GraphEngine | null>(null)
const engineReady = ref(false)
const loading = ref(true)

// ── Data ──
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const nodeCount = computed(() => nodes.value.length)
const edgeCount = computed(() => edges.value.length)

// ── Tooltip ──
const tooltipNode = ref<GraphNode | null>(null)
const hoveredEdgeRelation = ref<{ relation: string } | null>(null)
const tooltipTypeLabel = computed(() => {
  if (!tooltipNode.value) return ''
  return getTypeDisplay(tooltipNode.value.type)
})
const tooltipEdgeCount = computed(() => {
  if (!tooltipNode.value) return 0
  return edges.value.filter(e => e.source === tooltipNode.value!.id || e.target === tooltipNode.value!.id).length
})

// ── Filter state ──
const filterType = ref<string>('')
// Cache full unfiltered dataset for filter toggle restore
const fullNodes = ref<GraphNode[]>([])
const fullEdges = ref<GraphEdge[]>([])

// ── Detail sidebar ──
const selectedNode = ref<GraphNode | null>(null)
const selectedNodeDegree = computed(() => {
  if (!selectedNode.value) return 0
  return edges.value.filter(e => e.source === selectedNode.value!.id || e.target === selectedNode.value!.id).length
})
const relatedNodes = computed(() => {
  if (!selectedNode.value) return []
  const rel: { node: GraphNode; relation: string | undefined; color: string }[] = []
  const seen = new Set<number>()
  for (const e of edges.value) {
    let neighborId: number | null = null
    if (e.source === selectedNode.value.id) neighborId = e.target
    else if (e.target === selectedNode.value.id) neighborId = e.source
    if (neighborId !== null && !seen.has(neighborId)) {
      seen.add(neighborId)
      const node = nodes.value.find(n => n.id === neighborId)
      if (node) {
        rel.push({
          node,
          relation: e.relation,
          color: resolveNodeColor(node.type).hex,
        })
      }
    }
  }
  return rel.slice(0, 20)
})

// ── Search ──
const searchQuery = ref('')
const searchResults = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return []
  const matched: { node: GraphNode; color: string; typeLabel: string }[] = []
  for (const n of nodes.value) {
    if (n.label.toLowerCase().includes(q)) {
      matched.push({
        node: n,
        color: resolveNodeColor(n.type).hex,
        typeLabel: getTypeDisplay(n.type),
      })
      if (matched.length >= 20) break
    }
  }
  return matched
})

// ── Legend ──
interface LegendItem {
  type: string
  label: string
  color: string
  count: number
}
const legendItems = computed(() => {
  const typeCount = new Map<string, number>()
  for (const n of nodes.value) {
    typeCount.set(n.type, (typeCount.get(n.type) ?? 0) + 1)
  }
  const items: LegendItem[] = []
  for (const [type, count] of typeCount) {
    items.push({
      type,
      label: getTypeDisplay(type),
      color: resolveNodeColor(type).hex,
      count,
    })
  }
  // Sort by count descending
  items.sort((a, b) => b.count - a.count)
  return items
})

// ── Type helpers ──
function getTypeDisplay(type: string): string {
  // Direct match in English display labels
  if (typeDisplayLabels[type]) return typeDisplayLabels[type]
  // Try mapping Chinese category → English key → display label
  const englishKey = mapChineseCategory(type)
  if (typeDisplayLabels[englishKey]) return typeDisplayLabels[englishKey]
  // Fallback: return the type as-is
  return type
}

// ── Category mapping (preserve original category for color → type resolution) ──
interface RawNode {
  id: number
  label: string
  category: string
}

// ── Resize Observer ──
let resizeObserver: ResizeObserver | null = null
let visibilityObserver: IntersectionObserver | null = null

// ── Load data from API ──
async function loadData() {
  loading.value = true
  try {
    // Try entity-graph first, fall back to relation-graph
    const res = await fetch(getApiUrl('/knowledge/entity-graph'), {
      headers: authHeaders(),
    })
    const body = await res.json()
    if (body.success && body.data?.nodes?.length) {
      const data = body.data
      // Keep the original category for correct color resolution, but also set type
      const graphNodes: GraphNode[] = (data.nodes || []).map((n: any) => ({
        id: n.id,
        label: n.label,
        type: n.category || n.type || 'unknown',
        weight: n.weight ?? 0,
      }))
      const graphEdges: GraphEdge[] = (data.edges || []).map((e: any) => ({
        source: e.source,
        target: e.target,
        weight: e.weight ?? e.similarity_score ?? 0.5,
        relation: e.relation ?? '',
      }))

      if (graphNodes.length > 0) {
        nodes.value = graphNodes
        edges.value = graphEdges
        fullNodes.value = graphNodes
        fullEdges.value = graphEdges
        applyData()
        return
      }
    }

    // Fallback: relation-graph
    const res2 = await fetch(getApiUrl('/knowledge/relation-graph'), {
      headers: authHeaders(),
    })
    const body2 = await res2.json()
    if (body2.success && body2.data?.nodes?.length) {
      const data = body2.data
      const graphNodes: GraphNode[] = (data.nodes || []).map((n: any) => ({
        id: n.id,
        label: n.label,
        type: n.type || NodeType.Document,
        weight: 0,
      }))
      const graphEdges: GraphEdge[] = (data.edges || []).map((e: any) => ({
        source: e.source,
        target: e.target,
        weight: e.weight ?? e.similarity_score ?? 0.5,
        relation: e.relation_type ?? '',
      }))

      nodes.value = graphNodes
      edges.value = graphEdges
      fullNodes.value = graphNodes
      fullEdges.value = graphEdges
      applyData()
    } else {
      nodes.value = []
      edges.value = []
      loading.value = false
    }
  } catch (e) {
    console.error('[WorkspaceGraph] load error:', e)
    nodes.value = []
    edges.value = []
    loading.value = false
  }
}

function applyData() {
  if (!engine.value) return
  try {
    engine.value.setData(nodes.value, edges.value)
    engineReady.value = true
    loading.value = false
  } catch (e) {
    console.error('[WorkspaceGraph] applyData error:', e)
    loading.value = false
  }
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('v2_auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Search handlers ──
function onSearch() {
  if (!engine.value) return
  const q = searchQuery.value.trim().toLowerCase()
  if (q && searchResults.value.length > 0) {
    // Highlight all matched nodes
    const matchedIds = new Set(searchResults.value.map(r => r.node.id))
    for (const n of nodes.value) {
      const isMatched = matchedIds.has(n.id)
      if (engine.value.labelCtx) {
        engine.value.labelCtx.showForNode(n.id, isMatched)
      }
    }
    // Focus the first match
    focusNode(searchResults.value[0].node)
  } else {
    clearSearch()
  }
}

function clearSearch() {
  searchQuery.value = ''
  // Restore all label visibility
  if (engine.value?.labelCtx) {
    for (const n of nodes.value) {
      engine.value.labelCtx.showForNode(n.id, true)
    }
  }
  engine.value?.labelCtx?.showLabels(engine.value?.options?.labelDistanceThreshold ?? 120)
}

function focusNode(node: GraphNode) {
  if (!engine.value) return
  engine.value.focus(node.id)
  // Also highlight it
  if (engine.value.interactionCtx) {
    engine.value.interactionCtx.highlightNode(node.id)
  }
  selectedNode.value = node
  searchQuery.value = ''
}

// ── Filter handlers ──
function toggleFilter(type: string) {
  if (filterType.value === type) {
    // Clear filter — restore full data from cache
    filterType.value = ''
    nodes.value = fullNodes.value
    edges.value = fullEdges.value
    applyData()
  } else {
    filterType.value = type
    // Filter from full dataset, not current (which may already be filtered)
    const sourceNodes = fullNodes.value.length > 0 ? fullNodes.value : nodes.value
    const sourceEdges = fullEdges.value.length > 0 ? fullEdges.value : edges.value
    const filteredNodes = sourceNodes.filter(n => n.type === type)
    const filteredIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = sourceEdges.filter(e => filteredIds.has(e.source) && filteredIds.has(e.target))
    if (engine.value) {
      engine.value.setData(filteredNodes, filteredEdges)
    }
  }
}

// ── View controls ──
function resetView() {
  engine.value?.resetCamera()
}

function fitToView() {
  engine.value?.resetCamera()
}

// ── Detail handlers ──
function closeDetail() {
  selectedNode.value = null
}

function askAI(node: GraphNode) {
  // Use the platform module call to open agent with prefill
  try {
    const platform = (window as any).platform
    if (platform?.modules?.openApp) {
      platform.modules.openApp('agent', { prefill: { entity: node.label } })
    } else {
      window.open(`/desktop/agent?entity=${encodeURIComponent(node.label)}`, '_blank')
    }
  } catch {
    window.open(`/desktop/agent?entity=${encodeURIComponent(node.label)}`, '_blank')
  }
}

// ── Lifecycle ──
onMounted(async () => {
  await nextTick()
  const canvas = canvasRef.value
  if (!canvas) return

  // Create engine with reduced bloom
  const g = new GraphEngine(canvas, {
    backgroundColor: '#030812',
    bloomStrength: 0.3,
    bloomRadius: 0.2,
    bloomThreshold: 0.15,
    labelDistanceThreshold: 120,
    downgradeThreshold: 500,
  })

  // Listen for events
  g.on('select', (event: any) => {
    if (event?.node) {
      tooltipNode.value = event.node
      selectedNode.value = event.node
      // Also highlight and fly
      if (g.interactionCtx) {
        g.interactionCtx.highlightNode(event.node.id)
      }
      emit('select', event.node)
    } else {
      selectedNode.value = null
    }
  })
  g.on('hover', (event: any) => {
    tooltipNode.value = event?.node ?? null
    // Also check for edge hover when no node is hovered
    if (!event?.node && g.interactionCtx) {
      const edgeInfo = g.interactionCtx.getHoveredEdge()
      if (edgeInfo?.edge.relation) {
        hoveredEdgeRelation.value = { relation: edgeInfo.edge.relation }
      } else {
        hoveredEdgeRelation.value = null
      }
    } else {
      hoveredEdgeRelation.value = null
    }
  })

  g.init()
  engine.value = g

  // Visibility observer
  const container = containerRef.value
  if (container) {
    visibilityObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          entry.isIntersecting ? g.resume() : g.pause()
        }
      },
      { threshold: 0 },
    )
    visibilityObserver.observe(container)
  }

  // Resize observer
  resizeObserver = new ResizeObserver(() => {
    g.resize()
  })
  resizeObserver.observe(canvas.parentElement!)

  // Load data
  await loadData()
})

onUnmounted(() => {
  visibilityObserver?.disconnect()
  resizeObserver?.disconnect()
  engine.value?.dispose()
  engine.value = null
})
</script>

<style scoped>
.workspace-graph {
  flex: 1;
  min-height: 200px;
  position: relative;
  background: #030812;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid #1a2d42;
}

.graph-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

/* ── HUD overlay ── */
.hud-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 10;
}

/* ── Corner brackets ── */
.corner-brackets { position: absolute; inset: 0; }
.cb { position: absolute; width: 24px; height: 24px; }
.cb span { display: block; position: absolute; background: rgba(104,168,255,0.35); }
.cb span:first-child { width: 16px; height: 2px; }
.cb span:last-child { width: 2px; height: 16px; }

.cb-tl { top: 14px; left: 14px; }
.cb-tl span:first-child { top: 0; left: 0; }
.cb-tl span:last-child { top: 8px; left: 0; }

.cb-tr { top: 14px; right: 14px; }
.cb-tr span:first-child { top: 0; right: 0; }
.cb-tr span:last-child { top: 8px; right: 0; }

.cb-bl { bottom: 14px; left: 14px; }
.cb-bl span:first-child { bottom: 0; left: 0; }
.cb-bl span:last-child { bottom: 8px; left: 0; }

.cb-br { bottom: 14px; right: 14px; }
.cb-br span:first-child { bottom: 0; right: 0; }
.cb-br span:last-child { bottom: 8px; right: 0; }

/* ── Title + search ── */
.hud-title {
  position: absolute;
  top: 16px;
  left: 44px;
  pointer-events: auto;
}
.hud-title h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  font-family: 'Orbitron', 'system-ui', sans-serif;
  color: #e2edff;
  letter-spacing: 1px;
  text-shadow: 0 0 20px rgba(104,168,255,0.3);
}
.hud-subtitle {
  font-size: 9px;
  color: rgba(104,168,255,0.5);
  letter-spacing: 3px;
  font-family: 'Orbitron', 'system-ui', sans-serif;
  display: block;
  margin-top: 2px;
}

.search-box {
  margin-top: 8px;
  position: relative;
}
.search-input {
  width: 180px;
  padding: 5px 24px 5px 10px;
  border: 1px solid rgba(54,82,128,0.4);
  border-radius: 6px;
  background: rgba(4,12,28,0.85);
  color: #e2edff;
  font-size: 12px;
  font-family: 苹方, '微软雅黑', sans-serif;
  outline: none;
  transition: border-color 0.2s;
}
.search-input::placeholder { color: rgba(162,192,230,0.35); }
.search-input:focus { border-color: rgba(104,168,255,0.6); }
.search-clear {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: rgba(162,192,230,0.5);
  cursor: pointer;
  font-size: 11px;
  padding: 0;
  line-height: 1;
}

/* ── Stats ── */
.hud-stats {
  position: absolute;
  top: 20px;
  right: 44px;
  font-size: 11px;
  color: rgba(162,192,230,0.6);
  letter-spacing: 0.5px;
  font-variant-numeric: tabular-nums;
  pointer-events: auto;
}
.stat-divider { margin: 0 6px; opacity: 0.4; }
.stat-filter { color: rgba(240,184,72,0.6); }

/* ── View controls ── */
.hud-controls {
  position: absolute;
  top: 44px;
  right: 42px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  pointer-events: auto;
}
.ctrl-btn {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(54,82,128,0.3);
  border-radius: 6px;
  background: rgba(4,12,28,0.85);
  color: rgba(162,192,230,0.6);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.ctrl-btn:hover {
  background: rgba(54,82,128,0.3);
  color: #e2edff;
  border-color: rgba(104,168,255,0.5);
}

/* ── Legend ── */
.hud-legend {
  position: absolute;
  bottom: 44px;
  right: 20px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(4,12,28,0.92);
  border: 1px solid rgba(54,82,128,0.28);
  backdrop-filter: blur(14px);
  display: flex;
  flex-direction: column;
  gap: 4px;
  pointer-events: auto;
  min-width: 100px;
}
.legend-header {
  font-size: 10px;
  color: rgba(162,192,230,0.4);
  letter-spacing: 1px;
  margin-bottom: 2px;
  text-transform: uppercase;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.legend-item:hover { background: rgba(54,82,128,0.2); }
.legend-item.active { background: rgba(240,184,72,0.15); }
.legend-item.muted { opacity: 0.35; }
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
  box-shadow: 0 0 4px currentColor;
}
.legend-label {
  font-size: 11px;
  color: #bccbe0;
  font-family: 'system-ui', sans-serif;
  flex: 1;
}
.legend-count {
  font-size: 10px;
  color: rgba(162,192,230,0.35);
  font-variant-numeric: tabular-nums;
}

/* ── Tooltip ── */
.hud-tooltip {
  position: absolute;
  bottom: 44px;
  left: 20px;
  padding: 8px 14px;
  border-radius: 8px;
  background: rgba(4,12,28,0.92);
  border: 1px solid rgba(54,82,128,0.28);
  backdrop-filter: blur(14px);
  pointer-events: none;
}
.tt-name {
  font-size: 13px;
  font-weight: 600;
  color: #e2edff;
}
.tt-meta {
  font-size: 10px;
  color: #7c8da0;
  margin-top: 2px;
}

/* ── Edge tooltip ── */
.hud-edgetip {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 5px 12px;
  border-radius: 6px;
  background: rgba(4,12,28,0.9);
  border: 1px solid rgba(104,168,255,0.25);
  backdrop-filter: blur(8px);
  pointer-events: none;
  font-size: 11px;
  color: #68a8ff;
  letter-spacing: 0.5px;
  z-index: 15;
}
.et-arrow {
  color: rgba(104,168,255,0.4);
  margin-right: 4px;
}
.et-relation {
  color: #8cc4ff;
}

/* ── Search results ── */
.search-results {
  position: absolute;
  top: 100px;
  left: 44px;
  width: 220px;
  padding: 8px 0;
  border-radius: 8px;
  background: rgba(4,12,28,0.95);
  border: 1px solid rgba(54,82,128,0.35);
  backdrop-filter: blur(14px);
  pointer-events: auto;
  max-height: 260px;
  overflow-y: auto;
}
.sr-header {
  font-size: 10px;
  color: rgba(162,192,230,0.4);
  padding: 0 10px 6px;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.sr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  cursor: pointer;
  transition: background 0.1s;
}
.sr-item:hover { background: rgba(54,82,128,0.2); }
.sr-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.sr-label {
  font-size: 12px;
  color: #e2edff;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sr-type {
  font-size: 10px;
  color: rgba(162,192,230,0.4);
}

/* ── Scanline overlay ── */
.scanline-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 5;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(255,255,255,0.018) 2px,
    rgba(255,255,255,0.018) 4px
  );
}

/* ── Vignette ── */
.vignette-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 4;
  background: radial-gradient(ellipse at center, transparent 60%, rgba(1,4,8,0.6) 100%);
}

/* ── Loading ── */
.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: rgba(162,192,230,0.6);
  font-size: 13px;
  background: #030812;
  z-index: 20;
}
.loading-spinner {
  width: 32px;
  height: 32px;
  border: 2px solid rgba(104,168,255,0.15);
  border-top-color: rgba(104,168,255,0.7);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Empty ── */
.empty-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: rgba(162,192,230,0.5);
  font-size: 13px;
  z-index: 20;
  background: #030812;
}
.empty-icon {
  font-size: 28px;
  opacity: 0.4;
}

/* ── Detail sidebar ── */
.detail-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 260px;
  height: 100%;
  background: rgba(4,12,28,0.96);
  border-left: 1px solid rgba(54,82,128,0.35);
  backdrop-filter: blur(14px);
  z-index: 30;
  display: flex;
  flex-direction: column;
  pointer-events: auto;
  overflow: hidden;
}
.dp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(54,82,128,0.2);
}
.dp-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e2edff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.dp-close {
  background: none;
  border: none;
  color: rgba(162,192,230,0.4);
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
}
.dp-close:hover { color: #e2edff; }
.dp-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}
.dp-field {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12px;
}
.dp-label {
  color: rgba(162,192,230,0.4);
  min-width: 44px;
}
.dp-value { color: #bccbe0; }
.dp-section { margin-top: 14px; }
.dp-section-title {
  font-size: 11px;
  color: rgba(162,192,230,0.4);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.dp-rel-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.1s;
  font-size: 12px;
  margin-bottom: 2px;
}
.dp-rel-item:hover { background: rgba(54,82,128,0.2); }
.rel-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.rel-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rel-name { color: #bccbe0; }
.rel-type { color: rgba(162,192,230,0.35); font-size: 10px; }
.rel-edge-type {
  font-size: 9px;
  color: rgba(162,192,230,0.3);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dp-empty {
  font-size: 12px;
  color: rgba(162,192,230,0.25);
  padding: 8px 0;
}
.dp-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(54,82,128,0.2);
}
.dp-ai-btn {
  width: 100%;
  padding: 8px 0;
  border: 1px solid rgba(104,168,255,0.3);
  border-radius: 6px;
  background: rgba(104,168,255,0.08);
  color: #8cc4ff;
  font-size: 13px;
  font-family: 苹方, '微软雅黑', sans-serif;
  cursor: pointer;
  transition: all 0.15s;
}
.dp-ai-btn:hover {
  background: rgba(104,168,255,0.18);
  border-color: rgba(104,168,255,0.5);
}

/* ── Slide transition ── */
.slide-enter-active, .slide-leave-active {
  transition: transform 0.25s ease;
}
.slide-enter-from, .slide-leave-to {
  transform: translateX(100%);
}
</style>
