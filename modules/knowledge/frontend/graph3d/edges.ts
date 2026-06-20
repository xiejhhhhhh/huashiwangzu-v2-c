/**
 * Edge rendering: merged LineSegments with glow.
 *
 * Edges are drawn as a single LineSegments geometry (one per opacity/color tier).
 * Appearance: strong edges are brighter and thicker; weak edges are dim/near-transparent.
 */

/// <reference path="./three.d.ts" />

import { THREE } from './three-addons'
import { theme } from './theme'
import type { GraphEdge, GraphNode } from './types'
import type { LayoutPosition } from './layout3d'

/** Edge rendering context */
export interface EdgeRenderContext {
  strongLines: THREE.LineSegments
  weakLines: THREE.LineSegments
  dispose: () => void
}

/** Build edge visuals from layout + edge data */
export function buildEdges(
  nodes: GraphNode[],
  edges: GraphEdge[],
  positions: Map<number, LayoutPosition>,
  scene: THREE.Scene,
): EdgeRenderContext {
  if (edges.length === 0 || positions.size === 0) {
    const emptyGeo = new THREE.BufferGeometry()
    const emptyMat = new THREE.LineBasicMaterial()
    const empty = new THREE.LineSegments(emptyGeo, emptyMat)
    scene.add(empty)
    return {
      strongLines: empty,
      weakLines: empty,
      dispose() {},
    }
  }

  const nodeIds = new Set(nodes.map(n => n.id))
  const maxWeight = Math.max(1, ...edges.map(e => e.weight))

  // Split edges into strong (weight ≥ 0.4 * max) and weak
  const strongEdges: GraphEdge[] = []
  const weakEdges: GraphEdge[] = []
  for (const e of edges) {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue
    if (e.weight >= maxWeight * 0.4) {
      strongEdges.push(e)
    } else {
      weakEdges.push(e)
    }
  }

  const strongLines = buildLineSegments(strongEdges, positions, theme.edge.strong, 1.5)
  const weakLines = buildLineSegments(weakEdges, positions, theme.edge.weak, 0.8)

  scene.add(strongLines)
  scene.add(weakLines)

  return {
    strongLines,
    weakLines,
    dispose() {
      for (const lines of [strongLines, weakLines]) {
        scene.remove(lines)
        lines.geometry.dispose()
        if (Array.isArray(lines.material)) lines.material.forEach((m: THREE.Material) => m.dispose())
        else lines.material.dispose()
      }
    },
  }
}

/** Strip alpha from an rgba() string, returning the rgb() part */
function rgbaToRgb(color: string): string {
  const m = color.match(/^rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\d.]+\s*\)$/)
  if (m) return `rgb(${m[1]},${m[2]},${m[3]})`
  return color
}

/** Build a single LineSegments from a set of edges */
function buildLineSegments(
  edgeList: GraphEdge[],
  positions: Map<number, LayoutPosition>,
  color: string,
  lineWidth: number,
): THREE.LineSegments {
  const verts: number[] = []
  for (const e of edgeList) {
    const sp = positions.get(e.source)
    const tp = positions.get(e.target)
    if (!sp || !tp) continue
    verts.push(sp.x, sp.y, sp.z, tp.x, tp.y, tp.z)
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))

  const mat = new THREE.LineBasicMaterial({
    color: rgbaToRgb(color),
    transparent: true,
    opacity: 1,
    linewidth: lineWidth,
    depthWrite: false,
  })

  return new THREE.LineSegments(geo, mat)
}

/** Update edge positions when layout changes */
export function updateEdgePositions(
  ctx: EdgeRenderContext,
  edges: GraphEdge[],
  positions: Map<number, LayoutPosition>,
): void {
  const allEdges = edges

  const strongVerts: number[] = []
  const weakVerts: number[] = []
  const maxWeight = Math.max(1, ...allEdges.map(e => e.weight))

  for (const e of allEdges) {
    const sp = positions.get(e.source)
    const tp = positions.get(e.target)
    if (!sp || !tp) continue
    const verts = [sp.x, sp.y, sp.z, tp.x, tp.y, tp.z]
    if (e.weight >= maxWeight * 0.4) {
      strongVerts.push(...verts)
    } else {
      weakVerts.push(...verts)
    }
  }

  updateLinePositions(ctx.strongLines, strongVerts)
  updateLinePositions(ctx.weakLines, weakVerts)
}

function updateLinePositions(lines: THREE.LineSegments, verts: number[]): void {
  const geo = lines.geometry
  const pos = geo.getAttribute('position')
  if (pos && verts.length === pos.count * 3) {
    (pos as THREE.BufferAttribute).set(verts, 0)
    pos.needsUpdate = true
  } else {
    // Rebuild geometry
    geo.dispose()
    const newGeo = new THREE.BufferGeometry()
    newGeo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
    lines.geometry = newGeo
  }
}
