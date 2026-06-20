/**
 * Node labels: CSS2DRenderer overlay labels with distance-based visibility.
 *
 * Labels are HTML spans positioned via CSS2DRenderer.
 * Visibility toggles based on camera distance to avoid occlusion at long range.
 * Higher-degree / higher-weight nodes get priority visibility.
 */

/// <reference path="./three.d.ts" />

import { THREE, CSS2DRenderer, CSS2DObject } from './three-addons'
import { theme, resolveNodeColor } from './theme'
import type { GraphNode } from './types'
import type { LayoutPosition } from './layout3d'

/** Label rendering context */
export interface LabelRenderContext {
  renderer: CSS2DRenderer
  labels: Map<number, CSS2DObject>
  importanceOrder: number[]
  showLabels: (threshold: number) => void
  updatePositions: (positions: Map<number, LayoutPosition>) => void
  showForNode: (nodeId: number, visible: boolean) => void
  dispose: () => void
}

/** Compute importance score for a node (higher = more important) */
function computeImportance(node: GraphNode, edges: { source: number; target: number }[]): number {
  const degree = edges.filter(e => e.source === node.id || e.target === node.id).length
  return (node.weight ?? 0) * 2 + degree * 1.5 + (node.label ? node.label.length : 0) * 0.1
}

/** Create label renderer and populate labels */
export function buildLabels(
  nodes: GraphNode[],
  positions: Map<number, LayoutPosition>,
  container: HTMLElement,
  edges: { source: number; target: number }[] = [],
): LabelRenderContext {
  // ── CSS2DRenderer ──
  const renderer = new CSS2DRenderer()
  renderer.setSize(container.clientWidth, container.clientHeight)
  renderer.domElement.style.position = 'absolute'
  renderer.domElement.style.top = '0'
  renderer.domElement.style.left = '0'
  renderer.domElement.style.pointerEvents = 'none'
  container.appendChild(renderer.domElement)

  // ── Compute importance for LOD ──
  const importanceScores = new Map<number, number>()
  for (const node of nodes) {
    importanceScores.set(node.id, computeImportance(node, edges))
  }
  const importanceOrder = [...nodes]
    .sort((a, b) => (importanceScores.get(b.id) ?? 0) - (importanceScores.get(a.id) ?? 0))
    .map(n => n.id)

  // ── Create label elements ──
  const labels = new Map<number, CSS2DObject>()

  for (const node of nodes) {
    const pos = positions.get(node.id)
    if (!pos) continue

    const color = resolveNodeColor(node.type)
    const importance = importanceScores.get(node.id) ?? 0

    const div = document.createElement('div')
    div.textContent = node.label
    div.style.color = '#ffffff'
    div.style.fontSize = importance > 3 ? '12px' : '10px'
    div.style.fontWeight = importance > 5 ? '600' : '400'
    div.style.fontFamily = '苹方, "微软雅黑", sans-serif'
    div.style.textShadow = `0 0 4px ${color.hex}88, 0 0 12px rgba(0,0,0,0.9), 0 2px 4px rgba(0,0,0,0.8)`
    div.style.whiteSpace = 'nowrap'
    div.style.pointerEvents = 'none'
    div.style.userSelect = 'none'
    div.style.transition = 'opacity 0.2s ease'
    div.style.background = 'rgba(0,0,0,0.45)'
    div.style.padding = '1px 5px'
    div.style.borderRadius = '3px'
    div.style.border = `1px solid ${color.hex}44`
    div.style.backdropFilter = 'blur(2px)'
    div.style.letterSpacing = '0.3px'
    div.style.maxWidth = '160px'
    div.style.overflow = 'hidden'
    div.style.textOverflow = 'ellipsis'

    const label = new CSS2DObject(div)
    // Offset label slightly above the node
    const radius = importance > 5 ? 22 : 14
    label.position.set(pos.x, pos.y + radius + 4, pos.z)
    labels.set(node.id, label)
  }

  return {
    renderer,
    labels,
    importanceOrder,

    /** Toggle label visibility based on camera-to-node distance threshold */
    showLabels(threshold: number) {
      for (const [id, label] of labels) {
        const pos = positions.get(id)
        if (!pos) continue
        const dist = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z)
        const importance = importanceScores.get(id) ?? 0
        // Important nodes stay visible further away
        const effectiveThreshold = threshold * (1 + importance * 0.1)
        label.element.style.opacity = dist > effectiveThreshold ? '0' : '1'
      }
    },

    /** Reposition labels when layout changes */
    updatePositions(newPositions: Map<number, LayoutPosition>) {
      for (const [id, pos] of newPositions) {
        const label = labels.get(id)
        if (label) {
          const importance = importanceScores.get(id) ?? 0
          const radius = importance > 5 ? 22 : 14
          label.position.set(pos.x, pos.y + radius + 4, pos.z)
        }
      }
    },

    /** Show/hide a specific node's label */
    showForNode(nodeId: number, visible: boolean) {
      const label = labels.get(nodeId)
      if (label) {
        label.element.style.opacity = visible ? '1' : '0'
      }
    },

    dispose() {
      for (const label of labels.values()) {
        label.removeFromParent()
        label.element.remove()
      }
      labels.clear()
      renderer.domElement.remove()
      renderer.dispose()
    },
  }
}
