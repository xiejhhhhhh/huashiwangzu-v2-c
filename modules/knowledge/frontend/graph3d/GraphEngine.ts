/**
 * GraphEngine — the main entry point for the 3D knowledge graph.
 *
 * Orchestrates layout, scene, nodes, edges, labels, and interaction.
 * Pure TS — no Vue dependency. Can be tested independently.
 *
 * Usage:
 *   const engine = new GraphEngine(canvasElement, options)
 *   engine.setData(nodes, edges)
 *   engine.on('select', (event) => { ... })
 *   engine.dispose()  // cleanup on unmount
 */

import { type GraphEngineOptions, type GraphEngineEvent, type GraphNode, type GraphEdge, type SelectEvent, type HoverEvent } from './types'
import { computeLayout, type LayoutPosition } from './layout3d'
import { createScene, resizeScene, type SceneContext } from './scene'
import { buildNodes, type NodeRenderContext } from './nodes'
import { buildEdges, type EdgeRenderContext } from './edges'
import { buildLabels, type LabelRenderContext } from './labels'
import { setupInteraction, type InteractionContext } from './interaction'

type EventCallback = (event: any) => void

export class GraphEngine {
  readonly canvas: HTMLCanvasElement
  readonly options: Required<GraphEngineOptions>

  private sceneCtx: SceneContext | null = null
  private nodeCtx: NodeRenderContext | null = null
  private edgeCtx: EdgeRenderContext | null = null
  labelCtx: LabelRenderContext | null = null
  interactionCtx: InteractionContext | null = null

  nodes: GraphNode[] = []
  edges: GraphEdge[] = []
  positions: Map<number, LayoutPosition> = new Map()

  private listeners = new Map<GraphEngineEvent, EventCallback[]>()

  private animFrameId: number | null = null
  private isVisible = false
  private paused = false

  constructor(canvas: HTMLCanvasElement, options: GraphEngineOptions = {}) {
    this.canvas = canvas
    this.options = {
      backgroundColor: options.backgroundColor ?? '#030812',
      bloomStrength: options.bloomStrength ?? 0.6,
      bloomRadius: options.bloomRadius ?? 0.4,
      bloomThreshold: options.bloomThreshold ?? 0.1,
      maxPixelRatio: options.maxPixelRatio ?? 2,
      labelDistanceThreshold: options.labelDistanceThreshold ?? 120,
      downgradeThreshold: options.downgradeThreshold ?? 500,
      layoutIterations: options.layoutIterations ?? 150,
      bloomEnabled: options.bloomEnabled ?? true,
    }

    this.isVisible = true
  }

  /** Initialize the engine: create scene, start render loop */
  init(): void {
    if (this.sceneCtx) return // already initialized

    this.sceneCtx = createScene(this.canvas, this.options)
    this.startRenderLoop()
  }

  /** Set graph data (nodes + edges), compute layout, rebuild visuals */
  setData(nodes: GraphNode[], edges: GraphEdge[]): void {
    this.nodes = nodes
    this.edges = edges

    // Compute layout
    this.positions = computeLayout(nodes, edges, {
      maxIterations: this.options.layoutIterations,
    })

    // Rebuild scene objects
    this.rebuildVisuals()
  }

  /** Add nodes incrementally without full layout recompute */
  addNodes(newNodes: GraphNode[], allEdges: GraphEdge[]): void {
    this.edges = allEdges
    const existing = new Map<number, GraphNode>()
    for (const n of this.nodes) existing.set(n.id, n)
    const trulyNew = newNodes.filter(n => !existing.has(n.id))
    if (trulyNew.length === 0) return

    this.nodes = [...this.nodes, ...trulyNew]
    this.positions = computeLayout(this.nodes, this.edges, {
      maxIterations: this.options.layoutIterations,
    })

    this.rebuildVisuals()
  }

  /** Focus camera on a node (smooth fly-to) */
  focus(nodeId: number): void {
    const pos = this.positions.get(nodeId)
    if (pos && this.interactionCtx) {
      this.interactionCtx.controls.target.set(pos.x, pos.y, pos.z)
      this.interactionCtx.controls.update()
    }
  }

  /** Get position for a node */
  getNodePosition(nodeId: number): LayoutPosition | undefined {
    return this.positions.get(nodeId)
  }

  /** Reset camera to default position */
  resetCamera(): void {
    if (!this.sceneCtx || !this.interactionCtx) return
    const controls = this.interactionCtx.controls
    const camera = this.sceneCtx.camera
    // Animate reset
    const startPos = camera.position.clone()
    const startTarget = controls.target.clone()
    const endPos = { x: 0, y: 200, z: 500 }
    const endTarget = { x: 0, y: 0, z: 0 }
    const duration = 600
    const startTime = performance.now()

    function animate(t: number) {
      const elapsed = t - startTime
      const progress = Math.min(elapsed / duration, 1)
      const ease = progress < 0.5 ? 4 * progress * progress * progress : 1 - Math.pow(-2 * progress + 2, 3) / 2

      camera.position.lerpVectors(startPos, new THREE.Vector3(endPos.x, endPos.y, endPos.z), ease)
      controls.target.lerp(new THREE.Vector3(endTarget.x, endTarget.y, endTarget.z), ease)
      controls.update()

      if (progress < 1) requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }

  /** Resize (call when container dimensions change) */
  resize(): void {
    if (this.sceneCtx) resizeScene(this.sceneCtx)
    if (this.labelCtx) {
      const h = this.canvas.clientHeight
      const w = this.canvas.clientWidth
      this.labelCtx.renderer.setSize(w, h)
    }
  }

  /** Pause render loop (e.g. when tab is hidden) */
  pause(): void { this.paused = true }

  /** Resume render loop */
  resume(): void { this.paused = false }

  /** Subscribe to events */
  on(event: GraphEngineEvent, cb: EventCallback): void {
    const cbs = this.listeners.get(event) ?? []
    cbs.push(cb)
    this.listeners.set(event, cbs)
  }

  /** Unsubscribe from events */
  off(event: GraphEngineEvent, cb: EventCallback): void {
    const cbs = this.listeners.get(event)
    if (cbs) {
      this.listeners.set(event, cbs.filter(c => c !== cb))
    }
  }

  /** Set mode (for future mode switching — currently supports 'standard') */
  setMode(mode: string): void {
    if (mode === 'minimal' && this.sceneCtx) {
      this.sceneCtx.bloomPass.enabled = false
    } else if (this.sceneCtx) {
      this.sceneCtx.bloomPass.enabled = this.options.bloomEnabled
    }
  }

  /** Full cleanup — dispose all Three.js resources */
  dispose(): void {
    this.paused = true
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId)
      this.animFrameId = null
    }
    this.interactionCtx?.dispose()
    this.interactionCtx = null
    this.labelCtx?.dispose()
    this.labelCtx = null
    this.edgeCtx?.dispose()
    this.edgeCtx = null
    this.nodeCtx?.dispose()
    this.nodeCtx = null
    this.sceneCtx?.dispose()
    this.sceneCtx = null
    this.listeners.clear()
    this.isVisible = false
  }

  // ── Private ──

  private emit(event: GraphEngineEvent, payload: any): void {
    const cbs = this.listeners.get(event)
    if (cbs) cbs.forEach(cb => cb(payload))
  }

  private rebuildVisuals(): void {
    if (!this.sceneCtx) return
    const scene = this.sceneCtx.scene

    // Clean old visuals
    this.nodeCtx?.dispose()
    this.edgeCtx?.dispose()
    this.labelCtx?.dispose()

    // Build new
    this.nodeCtx = buildNodes(this.nodes, this.positions, scene, this.edges)
    this.edgeCtx = buildEdges(this.nodes, this.edges, this.positions, scene)

    // Labels (CSS2D) — need a container
    const labelContainer = this.canvas.parentElement!
    this.labelCtx = buildLabels(this.nodes, this.positions, labelContainer, this.edges)

    // Interaction
    this.interactionCtx?.dispose()
    this.interactionCtx = setupInteraction(
      this.sceneCtx,
      this.nodes,
      this.edges,
      this.positions,
      this.nodeCtx,
      this.edgeCtx,
      {
        onSelect: (node, pos) => this.emit('select', { node, position: pos } as SelectEvent),
        onHover: (node, pos) => this.emit('hover', { node, position: pos } as HoverEvent),
      },
      this.canvas,
    )

    // Update label visibility
    this.labelCtx.showLabels(this.options.labelDistanceThreshold)
    this.labelCtx.showLabels(this.options.labelDistanceThreshold)
  }

  private startRenderLoop(): void {
    const loop = () => {
      if (!this.paused && this.sceneCtx && this.interactionCtx) {
        this.interactionCtx.controls.update()
        this.sceneCtx.composer.render()
        this.labelCtx?.renderer.render(this.sceneCtx.scene, this.sceneCtx.camera)
      }
      this.animFrameId = requestAnimationFrame(loop)
    }
    this.animFrameId = requestAnimationFrame(loop)
  }
}

// Needed for resetCamera animation
import { THREE } from './three-addons'
