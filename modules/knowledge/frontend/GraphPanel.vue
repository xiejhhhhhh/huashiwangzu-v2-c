<template>
  <section class="graph-panel">
    <svg v-if="nodes.length" viewBox="0 0 720 360" role="img" aria-label="知识图谱">
      <line
        v-for="edge in graphEdges"
        :key="edge.id"
        :x1="positionMap.get(edge.source)?.x"
        :y1="positionMap.get(edge.source)?.y"
        :x2="positionMap.get(edge.target)?.x"
        :y2="positionMap.get(edge.target)?.y"
        stroke="#9db6d8"
        stroke-width="1.5"
      />
      <g v-for="edge in graphEdges" :key="`label-${edge.id}`">
        <text
          v-if="positionMap.get(edge.source) && positionMap.get(edge.target)"
          :x="labelPosition(edge).x"
          :y="labelPosition(edge).y"
          class="edge-label"
        >{{ edge.relation }}</text>
      </g>
      <g v-for="node in graphNodes" :key="node.id" class="node">
        <circle :cx="positionMap.get(node.id)?.x" :cy="positionMap.get(node.id)?.y" :r="node.id === centerNodeId ? 34 : 26" />
        <text :x="positionMap.get(node.id)?.x" :y="positionMap.get(node.id)?.y" text-anchor="middle" dominant-baseline="middle">
          {{ compactLabel(node.label) }}
        </text>
      </g>
    </svg>
    <div v-else class="graph-empty">选择实体后显示图谱上下文</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface GraphNode {
  id: number
  entity_id: number
  label: string
  category: string
}

export interface GraphEdge {
  id: number
  source: number
  target: number
  relation: string
}

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
  centerNodeId: number | null
}>()

const graphNodes = computed(() => props.nodes.slice(0, 16))
const graphEdges = computed(() => props.edges.filter((edge) => hasNode(edge.source) && hasNode(edge.target)))
const positionMap = computed(() => layoutNodes(graphNodes.value, props.centerNodeId))

function hasNode(id: number): boolean {
  return graphNodes.value.some((node) => node.id === id)
}

function layoutNodes(nodes: GraphNode[], centerNodeId: number | null): Map<number, { x: number; y: number }> {
  const map = new Map<number, { x: number; y: number }>()
  if (!nodes.length) return map
  const center = nodes.find((node) => node.id === centerNodeId) ?? nodes[0]
  map.set(center.id, { x: 360, y: 180 })
  const others = nodes.filter((node) => node.id !== center.id)
  const radius = 120
  others.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(others.length, 1) - Math.PI / 2
    map.set(node.id, {
      x: 360 + Math.cos(angle) * radius,
      y: 180 + Math.sin(angle) * radius,
    })
  })
  return map
}

function compactLabel(label: string): string {
  return label.length > 6 ? `${label.slice(0, 6)}…` : label
}

function labelPosition(edge: GraphEdge): { x: number; y: number } {
  const source = positionMap.value.get(edge.source)
  const target = positionMap.value.get(edge.target)
  if (!source || !target) return { x: 0, y: 0 }
  return { x: (source.x + target.x) / 2, y: (source.y + target.y) / 2 - 6 }
}
</script>

<style scoped>
.graph-panel {
  margin-top: 10px;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}

svg {
  display: block;
  width: 100%;
  height: 360px;
}

.node circle {
  fill: #eff6ff;
  stroke: #2563eb;
  stroke-width: 1.5;
}

.node text {
  fill: #1f2937;
  font-size: 12px;
  pointer-events: none;
}

.edge-label {
  fill: #64748b;
  font-size: 11px;
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
}

.graph-empty {
  padding: 24px;
  color: #6b7280;
  text-align: center;
}
</style>
