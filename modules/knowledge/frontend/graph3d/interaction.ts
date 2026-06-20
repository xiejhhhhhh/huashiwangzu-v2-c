/**
 * Interaction: OrbitControls + Raycaster-based hover, click, and focus.
 *
 * - OrbitControls: rotate/zoom/pan
 * - Hover: raycaster highlight (node + neighbors bright, others dim)
 * - Click: emit select event
 * - Double-click: camera fly-to focus
 * - Click empty space: clear highlight
 */

/// <reference path="./three.d.ts" />

import { THREE, OrbitControls } from './three-addons'

import { getNodeColor, getNodeRadius, resolveNodeColor } from './theme'
import type { GraphNode, GraphEdge } from './types'
import type { LayoutPosition } from './layout3d'
import type { SceneContext } from './scene'
import type { NodeRenderContext } from './nodes'
import type { EdgeRenderContext } from './edges'

/** Interaction callbacks */
export interface InteractionCallbacks {
  onSelect: (node: GraphNode, position: { x: number; y: number }) => void
  onHover: (node: GraphNode | null, position: { x: number; y: number }) => void
}

/** Interaction context */
export interface InteractionContext {
  controls: OrbitControls
  highlightNode: (nodeId: number | null) => void
  getHoveredEdge: () => { edge: GraphEdge; nodeA: GraphNode; nodeB: GraphNode } | null
  flyTo: (nodeId: number) => void
  dispose: () => void
}

const _dummyVec = new THREE.Vector3()

/** Build orbit controls and set up event listeners */
export function setupInteraction(
  scene: SceneContext,
  nodes: GraphNode[],
  edges: GraphEdge[],
  positions: Map<number, LayoutPosition>,
  nodeCtx: NodeRenderContext,
  edgeCtx: EdgeRenderContext,
  callbacks: InteractionCallbacks,
  canvas: HTMLCanvasElement,
): InteractionContext {
  // ── OrbitControls ──
  const controls = new OrbitControls(scene.camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.rotateSpeed = 0.8
  controls.zoomSpeed = 1.2
  controls.panSpeed = 0.5
  controls.minDistance = 80
  controls.maxDistance = 1200
  controls.target.set(0, 0, 0)

  // ── Raycaster ──
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()

  // Build a set of node IDs for quick lookup
  const nodeMap = new Map<number, GraphNode>()
  nodes.forEach(n => nodeMap.set(n.id, n))

  // Build adjacency for neighbor highlighting
  const adjacency = new Map<number, Set<number>>()
  for (const n of nodes) adjacency.set(n.id, new Set())
  for (const e of edges) {
    adjacency.get(e.source)?.add(e.target)
    adjacency.get(e.target)?.add(e.source)
  }

  // Edge index: for any pair (source,target), find the edge
  const edgeIndex = new Map<string, GraphEdge>()
  for (const e of edges) {
    // Store both directions
    edgeIndex.set(`${e.source}-${e.target}`, e)
    edgeIndex.set(`${e.target}-${e.source}`, e)
  }

  // Track highlight state
  let highlightedId: number | null = null
  let hoveredId: number | null = null

  // Store original sprite opacities
  const spriteOpacity = new Map<number, number>()

  // Hovered edge info
  let hoveredEdgeInfo: { edge: GraphEdge; nodeA: GraphNode; nodeB: GraphNode } | null = null

  /** Helper: get mouse position in normalized device coordinates */
  function getPointer(event: MouseEvent): THREE.Vector2 {
    const rect = canvas.getBoundingClientRect()
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    return pointer
  }

  /** Cast ray, return hit node id or null */
  function raycastNodes(event: MouseEvent): number | null {
    raycaster.setFromCamera(getPointer(event), scene.camera)

    // Collect all instanced meshes
    const meshes: THREE.InstancedMesh[] = []
    scene.scene.children.forEach((child: THREE.Object3D) => {
      if (child instanceof THREE.InstancedMesh) {
        meshes.push(child)
      }
    })

    const intersects = raycaster.intersectObjects(meshes)
    if (intersects.length > 0) {
      const hit = intersects[0]
      if (hit.instanceId !== undefined) {
        // Find closest node by position distance
        const hitPos = hit.point
        let closestNode: number | null = null
        let closestDist = 30
        for (const n of nodes) {
          const pos = positions.get(n.id)
          if (!pos) continue
          const dist = Math.sqrt(
            (pos.x - hitPos.x) ** 2 + (pos.y - hitPos.y) ** 2 + (pos.z - hitPos.z) ** 2,
          )
          if (dist < closestDist) {
            closestDist = dist
            closestNode = n.id
          }
        }
        return closestNode
      }
    }
    return null
  }

  /** Dim/restore all sprites */
  function dimAllSprites(dim: boolean) {
    for (const [id, entry] of nodeCtx.nodeMap) {
      if (!spriteOpacity.has(id)) {
        spriteOpacity.set(id, entry.sprite.material.opacity)
      }
      entry.sprite.material.opacity = dim ? 0.08 : (spriteOpacity.get(id) ?? 0.5)
    }
  }

  /** Highlight a node and its neighbors; dim the rest */
  function highlightNode(nodeId: number | null) {
    if (nodeId === highlightedId) return
    highlightedId = nodeId

    const neighborIds: Set<number> = nodeId ? (adjacency.get(nodeId) ?? new Set()) : new Set()

    // Dim all sprites first
    dimAllSprites(true)

    if (nodeId) {
      // Restore the highlighted node and its neighbors
      const brightSet = new Set([nodeId, ...neighborIds])
      for (const id of brightSet) {
        const entry = nodeCtx.nodeMap.get(id)
        if (entry) {
          entry.sprite.material.opacity = spriteOpacity.get(id) ?? 0.5
        }
      }
    }
  }

  /** Smooth fly-to animation */
  function flyTo(nodeId: number): void {
    const pos = positions.get(nodeId)
    if (!pos) return

    const targetPos = new THREE.Vector3(pos.x, pos.y, pos.z)
    const startPos = scene.camera.position.clone()
    const duration = 600
    const startTime = performance.now()

    function animateFly(time: number) {
      const t = Math.min((time - startTime) / duration, 1)
      const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2

      scene.camera.position.lerpVectors(startPos, targetPos.clone().add(new THREE.Vector3(0, 30, 120)), ease)
      controls.target.lerp(targetPos, ease)
      controls.update()

      if (t < 1) requestAnimationFrame(animateFly)
    }
    requestAnimationFrame(animateFly)
  }

  /** Find edge near pointer for hover (proximity to edge midpoint) */
  function findHoveredEdge(event: MouseEvent): { edge: GraphEdge; nodeA: GraphNode; nodeB: GraphNode } | null {
    raycaster.setFromCamera(getPointer(event), scene.camera)
    // Check each edge's midpoint distance
    let closest: { edge: GraphEdge; nodeA: GraphNode; nodeB: GraphNode; dist: number } | null = null
    for (const e of edges) {
      const sp = positions.get(e.source)
      const tp = positions.get(e.target)
      if (!sp || !tp) continue
      // Midpoint
      const mx = (sp.x + tp.x) / 2
      const my = (sp.y + tp.y) / 2
      const mz = (sp.z + tp.z) / 2
      // Project ray to find closest point on ray to midpoint
      const rayOrigin = raycaster.ray.origin
      const rayDir = raycaster.ray.direction
      const toMid = new THREE.Vector3(mx - rayOrigin.x, my - rayOrigin.y, mz - rayOrigin.z)
      const t = rayDir.dot(toMid)
      const closestOnRay = new THREE.Vector3(
        rayOrigin.x + rayDir.x * t,
        rayOrigin.y + rayDir.y * t,
        rayOrigin.z + rayDir.z * t,
      )
      const dist = Math.sqrt(
        (closestOnRay.x - mx) ** 2 + (closestOnRay.y - my) ** 2 + (closestOnRay.z - mz) ** 2,
      )
      if (dist < 15 && (closest === null || dist < closest.dist)) {
        closest = { edge: e, nodeA: nodeMap.get(e.source)!, nodeB: nodeMap.get(e.target)!, dist }
      }
    }
    return closest ? { edge: closest.edge, nodeA: closest.nodeA, nodeB: closest.nodeB } : null
  }

  // ── Event handlers ──

  let lastPointerMove = 0

  function onPointerMove(event: MouseEvent) {
    // Throttle raycaster to every 50ms
    const now = Date.now()
    if (now - lastPointerMove < 50) return
    lastPointerMove = now

    const id = raycastNodes(event)
    const rect = canvas.getBoundingClientRect()
    const pos = { x: event.clientX - rect.left, y: event.clientY - rect.top }

    if (id !== hoveredId) {
      hoveredId = id
      callbacks.onHover(id !== null ? nodeMap.get(id) ?? null : null, pos)
      highlightNode(id)
    }

    // Also check for edge hover
    if (id === null) {
      hoveredEdgeInfo = findHoveredEdge(event)
    } else {
      hoveredEdgeInfo = null
    }
  }

  function onClick(event: MouseEvent) {
    const id = raycastNodes(event)
    if (id !== null) {
      const node = nodeMap.get(id)
      if (node) {
        const rect = canvas.getBoundingClientRect()
        callbacks.onSelect(node, {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        })
      }
    } else {
      // Click empty space → clear highlight
      highlightNode(null)
      dimAllSprites(false)
      callbacks.onHover(null, { x: 0, y: 0 })
    }
  }

  function onDblClick(event: MouseEvent) {
    const id = raycastNodes(event)
    if (id !== null) {
      flyTo(id)
    }
  }

  canvas.addEventListener('pointermove', onPointerMove)
  canvas.addEventListener('click', onClick)
  canvas.addEventListener('dblclick', onDblClick)

  return {
    controls,
    highlightNode(nodeId: number | null) {
      highlightedId = null // force re-highlight
      highlightNode(nodeId)
    },
    getHoveredEdge() {
      return hoveredEdgeInfo
    },
    flyTo(nodeId: number) {
      flyTo(nodeId)
    },
    dispose() {
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('click', onClick)
      canvas.removeEventListener('dblclick', onDblClick)
      controls.dispose()
    },
  }
}
