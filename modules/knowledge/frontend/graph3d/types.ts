/**
 * Graph 3D Engine — data contracts.
 *
 * Pure TS types shared between the engine layer and business components.
 * No Three.js or Vue dependency in this file.
 */

/** Node type enum matching backend entity categories */
export const NodeType = {
  Subject: 'subject',
  Concept: 'concept',
  Tag: 'tag',
  Brand: 'brand',
  Document: 'document',
  Person: 'person',
  Location: 'location',
  Event: 'event',
  Unknown: 'unknown',
} as const

export type NodeType = (typeof NodeType)[keyof typeof NodeType]

/** A single graph node */
export interface GraphNode {
  id: number
  label: string
  type: NodeType | string
  /** Entity weight / degree — influences size */
  weight?: number
  /** Optional extra metadata */
  meta?: Record<string, unknown>
}

/** A single graph edge */
export interface GraphEdge {
  source: number
  target: number
  weight: number
  /** Relation type label (optional, shown in tooltip) */
  relation?: string
}

/** Node type → (color token key, base radius) */
export interface NodeTypeVisual {
  colorKey: string
  baseRadius: number
}

/** Engine configuration passed at construction */
export interface GraphEngineOptions {
  /** Background color (default: #030812) */
  backgroundColor?: string
  /** Bloom strength (default: 0.6) */
  bloomStrength?: number
  /** Bloom radius (default: 0.4) */
  bloomRadius?: number
  /** Bloom threshold (default: 0.1) */
  bloomThreshold?: number
  /** Max DPR for HiDPI rendering (default: 2) */
  maxPixelRatio?: number
  /** Level-of-detail: hide labels when camera is this far away (default: 120) */
  labelDistanceThreshold?: number
  /** Auto-downgrade node count threshold (default: 500) */
  downgradeThreshold?: number
  /** Layout iterations (default: 150) */
  layoutIterations?: number
  /** Enable/disable bloom (default: true) */
  bloomEnabled?: boolean
}

/** Event types emitted by GraphEngine */
export type GraphEngineEvent = 'select' | 'hover' | 'blur'

/** Event payload for select */
export interface SelectEvent {
  node: GraphNode
  /** Canvas mouse position */
  position: { x: number; y: number }
}

/** Event payload for hover */
export interface HoverEvent {
  node: GraphNode | null
  /** Canvas mouse position */
  position: { x: number; y: number }
}
