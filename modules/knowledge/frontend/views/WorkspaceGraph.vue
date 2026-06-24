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
import { GraphEngine } from '../graph3d/GraphEngine'
import { computeLayout } from '../graph3d/layout3d'
import { theme, resolveNodeColor, getNodeColor, getNodeRadius, nodeTypeVisualMap, typeDisplayLabels, mapChineseCategory } from '../graph3d/theme'
import { NodeType, type GraphNode, type GraphEdge } from '../graph3d/types'
import { getEntityGraph, getRelationGraph, type EntityGraphNode, type EntityGraphEdge, type RelationGraphNode, type RelationGraphEdge } from '../api'

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
    const data = await getEntityGraph()
    if (data.nodes?.length) {
      // Keep the original category for correct color resolution, but also set type
      const graphNodes: GraphNode[] = (data.nodes || []).map((n: EntityGraphNode) => ({
        id: n.id,
        label: n.label,
        type: n.category || n.type || 'unknown',
        weight: n.weight ?? 0,
      }))
      const graphEdges: GraphEdge[] = (data.edges || []).map((e: EntityGraphEdge) => ({
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
    const data2 = await getRelationGraph()
    if (data2.nodes?.length) {
      const graphNodes: GraphNode[] = (data2.nodes || []).map((n: RelationGraphNode) => ({
        id: n.id,
        label: n.label,
        type: n.type || NodeType.Document,
        weight: 0,
      }))
      const graphEdges: GraphEdge[] = (data2.edges || []).map((e: RelationGraphEdge) => ({
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

// ── Search handlers ──
function onSearch() {
  if (!engine.value) return
  const q = searchQuery.value.trim().toLowerCase()
  if (q && searchResults.value.length > 0) {
    // Highlight all matched nodes via card fade
    const matchedIds = new Set(searchResults.value.map(r => r.node.id))
    if (engine.value.nodeCtx) {
      for (const n of nodes.value) {
        const isMatched = matchedIds.has(n.id)
        engine.value.nodeCtx.fadeTo(n.id, isMatched ? 1 : 0.12)
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
  // Restore all card visibility
  if (engine.value?.nodeCtx) {
    engine.value.nodeCtx.fadeAll(1)
  }
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
    const platform = window.platform
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
  g.on('select', (event: unknown) => {
    const ev = event as { node?: GraphNode } | null
    if (ev?.node) {
      tooltipNode.value = ev.node
      selectedNode.value = ev.node
      if (g.interactionCtx) {
        g.interactionCtx.highlightNode(ev.node.id)
      }
      emit('select', ev.node)
    } else {
      selectedNode.value = null
    }
  })
  g.on('hover', (event: unknown) => {
    const ev = event as { node?: GraphNode } | null
    tooltipNode.value = ev?.node ?? null
    if (!ev?.node && g.interactionCtx) {
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

<style scoped src="./WorkspaceGraph.style.css"></style>
