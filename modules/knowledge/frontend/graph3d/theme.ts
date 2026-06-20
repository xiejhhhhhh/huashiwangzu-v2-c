/**
 * Deep-space HUD color theme — HoloGram-compatible token palette.
 *
 * All visual tokens live here so the engine can be re-themed by swapping this file.
 */

import { NodeType } from './types'

/** Color hex string */
export type HexColor = string

/** RGBA string */
export type RGBAColor = string

/** A semantic color token set */
export interface ColorToken {
  hex: HexColor
  bright?: HexColor
  glow: RGBAColor
}

/** Theme palette — every visual constant */
export interface ThemePalette {
  /** Background colors */
  bg: {
    void: HexColor
    voidDeep: HexColor
  }
  /** Text / UI */
  text: {
    starlight: HexColor
    muted: HexColor
  }
  /** Node type colors */
  node: {
    subject: ColorToken      // 金 sol
    concept: ColorToken      // 蓝 signal
    tag: ColorToken          // 紫 nebula
    brand: ColorToken        // 亮蓝 signal-bright
    document: ColorToken     // 星光白 starlight
    person: ColorToken       // 绿
    location: ColorToken     // 橙
    event: ColorToken        // 亮蓝
    unknown: ColorToken
  }
  /** Edge colors */
  edge: {
    strong: RGBAColor
    weak: RGBAColor
    neutral: RGBAColor
  }
  /** Panels */
  panel: {
    bg: RGBAColor
    edge: RGBAColor
    blur: string
  }
  /** Status */
  status: {
    error: HexColor
    warning: HexColor
    success: HexColor
  }
  /** Atmosphere */
  atmosphere: {
    scanlineOpacity: number
    vignetteColor: RGBAColor
  }
}

/** Full theme palette */
export const theme: ThemePalette = {
  bg: {
    void: '#030812',
    voidDeep: '#010408',
  },
  text: {
    starlight: '#e2edff',
    muted: '#7c8da0',
  },
  node: {
    subject: { hex: '#f0b848', bright: '#ffcc60', glow: 'rgba(240,170,50,0.30)' },
    concept: { hex: '#68a8ff', bright: '#8cc4ff', glow: 'rgba(80,140,240,0.35)' },
    tag: { hex: '#a088e0', bright: '#c0a8ff', glow: 'rgba(140,110,220,0.25)' },
    brand: { hex: '#8cc4ff', bright: '#b0dcff', glow: 'rgba(100,180,255,0.30)' },
    document: { hex: '#e2edff', bright: '#ffffff', glow: 'rgba(200,220,240,0.15)' },
    person: { hex: '#48cc68', bright: '#60e880', glow: 'rgba(72,204,104,0.30)' },
    location: { hex: '#f07838', bright: '#ff9050', glow: 'rgba(240,120,56,0.30)' },
    event: { hex: '#8cc4ff', bright: '#b0dcff', glow: 'rgba(100,180,255,0.30)' },
    unknown: { hex: '#8aa0b5', bright: '#aab8c6', glow: 'rgba(100,120,140,0.15)' },
  },
  edge: {
    strong: 'rgba(104,168,255,0.55)',
    weak: 'rgba(104,168,255,0.12)',
    neutral: 'rgba(104,168,255,0.28)',
  },
  panel: {
    bg: 'rgba(4,12,28,0.92)',
    edge: 'rgba(54,82,128,0.28)',
    blur: 'blur(14px)',
  },
  status: {
    error: '#f04848',
    warning: '#f07838',
    success: '#48cc68',
  },
  atmosphere: {
    scanlineOpacity: 0.018,
    vignetteColor: 'rgba(1,4,8,0.60)',
  },
}

/** Default node type → visual mapping */
export const nodeTypeVisualMap: Record<string, { color: ColorToken; baseRadius: number }> = {
  [NodeType.Subject]: { color: theme.node.subject, baseRadius: 22 },
  [NodeType.Concept]: { color: theme.node.concept, baseRadius: 16 },
  [NodeType.Tag]: { color: theme.node.tag, baseRadius: 11 },
  [NodeType.Brand]: { color: theme.node.brand, baseRadius: 16 },
  [NodeType.Document]: { color: theme.node.document, baseRadius: 13 },
  [NodeType.Person]: { color: theme.node.person, baseRadius: 14 },
  [NodeType.Location]: { color: theme.node.location, baseRadius: 14 },
  [NodeType.Event]: { color: theme.node.event, baseRadius: 14 },
  [NodeType.Unknown]: { color: theme.node.unknown, baseRadius: 12 },
}

/** Get effective node radius by type and weight */
export function getNodeRadius(type: string, weight?: number, degree?: number): number {
  const entry = nodeTypeVisualMap[type] ?? nodeTypeVisualMap[NodeType.Unknown]
  const scale = 1 + Math.min((weight ?? 0) * 0.3 + (degree ?? 0) * 0.08, 1.5)
  return entry.baseRadius * scale
}

/** Get node color by type */
export function getNodeColor(type: string): ColorToken {
  return nodeTypeVisualMap[type]?.color ?? theme.node.unknown
}

// ── Chinese category → type key mapping ──

/** Chinese category strings from the entity extractor → English type keys */
export const chineseCategoryMap: Record<string, string> = {
  '术语': NodeType.Concept,
  '产品名': NodeType.Brand,
  '产品': NodeType.Brand,
  '其他': NodeType.Unknown,
  '事件': NodeType.Event,
  '组织': NodeType.Subject,
  '组织名': NodeType.Subject,
  '地名': NodeType.Location,
  '人名': NodeType.Person,
}

/** Get English type key from Chinese category string */
export function mapChineseCategory(category: string): string {
  return chineseCategoryMap[category] ?? category
}

/** Hash a string to a hue value (0-360) */
function hashCode(s: string): number {
  let hash = 0
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) - hash) + s.charCodeAt(i)
    hash |= 0 // Convert to 32-bit int
  }
  return Math.abs(hash)
}

/** Assign a stable distinct color for any arbitrary category name (hash-based HSL).
 *  Produces distinct hues for different category names, with consistent saturation/lightness. */
export function hashCategoryColorToken(category: string): ColorToken {
  const h = hashCode(category) % 360
  // Use golden angle (137.5°) offset so adjacent categories get distinct hues
  const hue = (h + 137) % 360
  // Keep saturation and lightness moderate for readability on dark bg
  const sat = 55 + (hashCode(category + 's') % 20) // 55-75%
  const light = 55 + (hashCode(category + 'l') % 15) // 55-70%
  const hex = hslToHex(hue, sat, light)
  const glowLight = Math.max(30, light - 25)
  return {
    hex,
    bright: hslToHex(hue, sat, Math.min(85, light + 15)),
    glow: `hsla(${hue}, ${sat - 10}%, ${glowLight}%, 0.25)`,
  }
}

function hslToHex(h: number, s: number, l: number): string {
  s /= 100
  l /= 100
  const a = s * Math.min(l, 1 - l)
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
    return Math.round(255 * color).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

/** Resolve color for a node type string — supports English keys, Chinese categories,
 *  and hash fallback for any unrecognized string. */
export function resolveNodeColor(categoryOrType: string): ColorToken {
  // Direct match in visual map (English key)
  if (nodeTypeVisualMap[categoryOrType]) {
    return nodeTypeVisualMap[categoryOrType].color
  }
  // Chinese category mapping
  const englishKey = mapChineseCategory(categoryOrType)
  if (nodeTypeVisualMap[englishKey]) {
    return nodeTypeVisualMap[englishKey].color
  }
  // Hash-based fallback for arbitrary category names
  return hashCategoryColorToken(categoryOrType)
}

/** Resolve display label for a node type (shows Chinese where applicable) */
export const typeDisplayLabels: Record<string, string> = {
  [NodeType.Subject]: '主体',
  [NodeType.Concept]: '概念',
  [NodeType.Tag]: '标签',
  [NodeType.Brand]: '品牌',
  [NodeType.Document]: '文件',
  [NodeType.Person]: '人名',
  [NodeType.Location]: '地名',
  [NodeType.Event]: '事件',
  [NodeType.Unknown]: '其他',
}
