/**
 * 拖拽工具函数 — 网格吸附 + 边界检测
 *
 * 图标是 flex 布局，不设绝对坐标。
 * 拖拽结束后通过 transform 偏移实现视觉落点，
 * 落点坐标存储用于后续持久化。
 */
import { reactive } from 'vue'
import { readIconPositions, updateIconPositions } from './icon-position-store'

const ICON_W = 88
const ICON_H = 88
const TASKBAR_H = 48
const DEFAULT_GRID_ORIGIN_X = 12
const DEFAULT_GRID_ORIGIN_Y = 26
const DEFAULT_GRID_STEP_X = 92
const DEFAULT_GRID_STEP_Y = 94

function readPixelValue(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function getIconGridMetrics(): {
  originX: number
  originY: number
  stepX: number
  stepY: number
  iconWidth: number
  iconHeight: number
  maxX: number
  maxY: number
} {
  const grid = document.querySelector('.desktop-icon-grid') as HTMLElement | null
  const icon = document.querySelector('.desktop-icon-item') as HTMLElement | null
  const taskbar = document.querySelector('.desktop-taskbar') as HTMLElement | null
  if (!grid || !icon) {
    return {
      originX: DEFAULT_GRID_ORIGIN_X,
      originY: DEFAULT_GRID_ORIGIN_Y,
      stepX: DEFAULT_GRID_STEP_X,
      stepY: DEFAULT_GRID_STEP_Y,
      iconWidth: ICON_W,
      iconHeight: ICON_H,
      maxX: window.innerWidth - ICON_W,
      maxY: window.innerHeight - TASKBAR_H - ICON_H,
    }
  }

  const gridRect = grid.getBoundingClientRect()
  const gridStyle = window.getComputedStyle(grid)
  const iconWidth = icon.offsetWidth || ICON_W
  const iconHeight = icon.offsetHeight || ICON_H
  const gapX = readPixelValue(gridStyle.columnGap) || readPixelValue(gridStyle.gap.split(' ')[1] || gridStyle.gap)
  const gapY = readPixelValue(gridStyle.rowGap) || readPixelValue(gridStyle.gap.split(' ')[0] || gridStyle.gap)
  const stepX = Math.max(iconWidth + gapX, 1)
  const stepY = Math.max(iconHeight + gapY, 1)
  const availableBottom = taskbar?.getBoundingClientRect().top ?? window.innerHeight - TASKBAR_H

  return {
    originX: gridRect.left + readPixelValue(gridStyle.paddingLeft),
    originY: gridRect.top + readPixelValue(gridStyle.paddingTop),
    stepX,
    stepY,
    iconWidth,
    iconHeight,
    maxX: window.innerWidth - iconWidth,
    maxY: availableBottom - iconHeight,
  }
}

function snapToSlot(value: number, origin: number, step: number, max: number): number {
  const maxSlot = origin + Math.max(0, Math.floor((max - origin) / step)) * step
  const snapped = origin + Math.round((value - origin) / step) * step
  return Math.max(origin, Math.min(snapped, maxSlot))
}

function positionToSlot(position: { x: number; y: number }, metrics: ReturnType<typeof getIconGridMetrics>): { col: number; row: number } {
  return {
    col: Math.max(0, Math.round((position.x - metrics.originX) / metrics.stepX)),
    row: Math.max(0, Math.round((position.y - metrics.originY) / metrics.stepY)),
  }
}

function slotToPosition(slot: { col?: number; row?: number; x: number; y: number }, metrics: ReturnType<typeof getIconGridMetrics>): { x: number; y: number } {
  const col = typeof slot.col === 'number' && Number.isFinite(slot.col)
    ? slot.col
    : Math.max(0, Math.round((slot.x - metrics.originX) / metrics.stepX))
  const row = typeof slot.row === 'number' && Number.isFinite(slot.row)
    ? slot.row
    : Math.max(0, Math.round((slot.y - metrics.originY) / metrics.stepY))
  return {
    x: snapToSlot(metrics.originX + col * metrics.stepX, metrics.originX, metrics.stepX, metrics.maxX),
    y: snapToSlot(metrics.originY + row * metrics.stepY, metrics.originY, metrics.stepY, metrics.maxY),
  }
}

function slotKey(x: number, y: number): string {
  return `${Math.round(x)}:${Math.round(y)}`
}

function getElementTranslateOffset(el: Element): { x: number; y: number } {
  const transform = window.getComputedStyle(el).transform
  if (!transform || transform === 'none') return { x: 0, y: 0 }
  const matrix3d = transform.match(/^matrix3d\((.+)\)$/)
  if (matrix3d) {
    const parts = matrix3d[1].split(',').map(part => Number(part.trim()))
    return { x: Number.isFinite(parts[12]) ? parts[12] : 0, y: Number.isFinite(parts[13]) ? parts[13] : 0 }
  }
  const matrix = transform.match(/^matrix\((.+)\)$/)
  if (!matrix) return { x: 0, y: 0 }
  const parts = matrix[1].split(',').map(part => Number(part.trim()))
  return { x: Number.isFinite(parts[4]) ? parts[4] : 0, y: Number.isFinite(parts[5]) ? parts[5] : 0 }
}

function getOccupiedSlots(metrics: ReturnType<typeof getIconGridMetrics>, excludedKeys: string[]): Set<string> {
  const excluded = new Set(excludedKeys)
  const occupied = new Set<string>()
  document.querySelectorAll('.desktop-icon-item').forEach(el => {
    const key = el.getAttribute('data-selection-key')
    if (!key || excluded.has(key)) return
    const rect = el.getBoundingClientRect()
    const x = snapToSlot(rect.left, metrics.originX, metrics.stepX, metrics.maxX)
    const y = snapToSlot(rect.top, metrics.originY, metrics.stepY, metrics.maxY)
    occupied.add(slotKey(x, y))
  })
  return occupied
}

function findAvailableSlot(
  target: { x: number; y: number },
  metrics: ReturnType<typeof getIconGridMetrics>,
  occupied: Set<string>,
): { x: number; y: number } {
  if (!occupied.has(slotKey(target.x, target.y))) return target

  const columnCount = Math.max(1, Math.floor((metrics.maxX - metrics.originX) / metrics.stepX) + 1)
  const rowCount = Math.max(1, Math.floor((metrics.maxY - metrics.originY) / metrics.stepY) + 1)
  const startCol = Math.max(0, Math.round((target.x - metrics.originX) / metrics.stepX))
  const startRow = Math.max(0, Math.round((target.y - metrics.originY) / metrics.stepY))
  const totalSlots = columnCount * rowCount

  for (let i = 1; i < totalSlots; i += 1) {
    const index = startCol * rowCount + startRow + i
    const col = Math.floor(index / rowCount) % columnCount
    const row = index % rowCount
    const x = metrics.originX + col * metrics.stepX
    const y = metrics.originY + row * metrics.stepY
    if (!occupied.has(slotKey(x, y))) return { x, y }
  }

  return target
}

/** 按桌面图标实际槽位吸附并限制边界 */
export function clampIconPosition(x: number, y: number): { x: number; y: number } {
  const metrics = getIconGridMetrics()
  return {
    x: snapToSlot(x, metrics.originX, metrics.stepX, metrics.maxX),
    y: snapToSlot(y, metrics.originY, metrics.stepY, metrics.maxY),
  }
}

/**
 * 拖拽落点坐标覆盖表
 * key: data-selection-key value, for example "file:123"
 * value: 落点 transform 偏移 { x, y }
 *
 * 图标渲染时读取此表，有覆盖则用 transform 偏移，
 * 无覆盖则回到 flex 默认位置。
 */
export const dropOverlay = reactive<Record<string, { x: number; y: number }>>({})

export function setDropOverlay(key: string, x: number, y: number): void {
  dropOverlay[key] = { x, y }
}

export function setDropOverlayBatch(
  primaryKey: string, primaryX: number, primaryY: number,
  allKeys: string[], offsetList: { id: string; dx: number; dy: number; baseLeft: number; baseTop: number }[]
): void {
  const metrics = getIconGridMetrics()
  const occupied = getOccupiedSlots(metrics, allKeys)
  allKeys.forEach(key => {
    const offset = offsetList.find(o => o.id === key)
    const snapped = {
      x: snapToSlot(key === primaryKey ? primaryX : primaryX + (offset?.dx ?? 0), metrics.originX, metrics.stepX, metrics.maxX),
      y: snapToSlot(key === primaryKey ? primaryY : primaryY + (offset?.dy ?? 0), metrics.originY, metrics.stepY, metrics.maxY),
    }
    const target = findAvailableSlot(snapped, metrics, occupied)
    occupied.add(slotKey(target.x, target.y))
    updateIconPositions({ [key]: { ...positionToSlot(target, metrics), ...target } })
    dropOverlay[key] = {
      x: target.x - (offset?.baseLeft ?? 0),
      y: target.y - (offset?.baseTop ?? 0),
    }
  })
}

export function resolveDropOverlayBatch(
  primaryKey: string, primaryX: number, primaryY: number,
  allKeys: string[], offsetList: { id: string; dx: number; dy: number; baseLeft: number; baseTop: number }[],
): Record<string, { x: number; y: number }> {
  const metrics = getIconGridMetrics()
  const occupied = getOccupiedSlots(metrics, allKeys)
  const result: Record<string, { x: number; y: number }> = {}

  allKeys.forEach(key => {
    const offset = offsetList.find(o => o.id === key)
    const snapped = {
      x: snapToSlot(key === primaryKey ? primaryX : primaryX + (offset?.dx ?? 0), metrics.originX, metrics.stepX, metrics.maxX),
      y: snapToSlot(key === primaryKey ? primaryY : primaryY + (offset?.dy ?? 0), metrics.originY, metrics.stepY, metrics.maxY),
    }
    const target = findAvailableSlot(snapped, metrics, occupied)
    occupied.add(slotKey(target.x, target.y))
    result[key] = {
      x: target.x - (offset?.baseLeft ?? 0),
      y: target.y - (offset?.baseTop ?? 0),
    }
  })

  return result
}

export function setDropOverlayBatchFromOffsets(offsets: Record<string, { x: number; y: number }>): void {
  Object.entries(offsets).forEach(([key, value]) => {
    dropOverlay[key] = value
  })
}

export function commitDropOverlayBatch(
  primaryKey: string, primaryX: number, primaryY: number,
  allKeys: string[], offsetList: { id: string; dx: number; dy: number; baseLeft: number; baseTop: number }[],
): Record<string, { x: number; y: number }> {
  const metrics = getIconGridMetrics()
  const occupied = getOccupiedSlots(metrics, allKeys)
  const offsets: Record<string, { x: number; y: number }> = {}
  const positions: Record<string, { x: number; y: number }> = {}

  allKeys.forEach(key => {
    const offset = offsetList.find(o => o.id === key)
    const snapped = {
      x: snapToSlot(key === primaryKey ? primaryX : primaryX + (offset?.dx ?? 0), metrics.originX, metrics.stepX, metrics.maxX),
      y: snapToSlot(key === primaryKey ? primaryY : primaryY + (offset?.dy ?? 0), metrics.originY, metrics.stepY, metrics.maxY),
    }
    const target = findAvailableSlot(snapped, metrics, occupied)
    occupied.add(slotKey(target.x, target.y))
    positions[key] = { ...positionToSlot(target, metrics), ...target }
    offsets[key] = {
      x: target.x - (offset?.baseLeft ?? 0),
      y: target.y - (offset?.baseTop ?? 0),
    }
  })

  updateIconPositions(positions)
  setDropOverlayBatchFromOffsets(offsets)
  return offsets
}

export function restorePersistedIconPositions(): void {
  const positions = readIconPositions()
  const metrics = getIconGridMetrics()

  // First pass: set dropOverlay for all items with stored positions,
  // and build a set of targeted absolute grid slots
  const targetedSlots = new Set<string>()
  const overlayUpdates: Record<string, { x: number; y: number }> = {}

  document.querySelectorAll('.desktop-icon-item').forEach(el => {
    const key = el.getAttribute('data-selection-key')
    if (!key) return
    const position = positions[key]
    if (!position) return
    const targetX = snapToSlot(
      typeof position.col === 'number' ? metrics.originX + position.col * metrics.stepX : position.x,
      metrics.originX, metrics.stepX, metrics.maxX
    )
    const targetY = snapToSlot(
      typeof position.row === 'number' ? metrics.originY + position.row * metrics.stepY : position.y,
      metrics.originY, metrics.stepY, metrics.maxY
    )
    const offset = getElementTranslateOffset(el)
    const rect = el.getBoundingClientRect()
    const baseLeft = rect.left - offset.x
    const baseTop = rect.top - offset.y
    const slot = slotKey(targetX, targetY)
    targetedSlots.add(slot)
    overlayUpdates[key] = { x: targetX - baseLeft, y: targetY - baseTop }
  })

  // Apply all overlays
  Object.entries(overlayUpdates).forEach(([key, val]) => {
    dropOverlay[key] = val
  })

  // Second pass: detect items without stored positions that conflict with targeted slots
  document.querySelectorAll('.desktop-icon-item').forEach(el => {
    const key = el.getAttribute('data-selection-key')
    if (!key || positions[key]) return
    const rect = el.getBoundingClientRect()
    const flexSlot = slotKey(
      snapToSlot(rect.left, metrics.originX, metrics.stepX, metrics.maxX),
      snapToSlot(rect.top, metrics.originY, metrics.stepY, metrics.maxY)
    )
    if (targetedSlots.has(flexSlot)) {
      // This item's flex slot is taken by a positioned item — move it to nearest free slot
      const snapshot: Record<string, { x: number; y: number }> = {}
      const currentOccupied = new Set(targetedSlots)
      document.querySelectorAll('.desktop-icon-item').forEach(other => {
        const otherKey = other.getAttribute('data-selection-key')
        if (!otherKey || otherKey === key) return
        const o = getElementTranslateOffset(other)
        const r = other.getBoundingClientRect()
        const s = slotKey(
          snapToSlot(r.left - o.x + (dropOverlay[otherKey]?.x ?? 0), metrics.originX, metrics.stepX, metrics.maxX),
          snapToSlot(r.top - o.y + (dropOverlay[otherKey]?.y ?? 0), metrics.originY, metrics.stepY, metrics.maxY)
        )
        currentOccupied.add(s)
      })
      const free = findAvailableSlot(
        { x: rect.left, y: rect.top },
        metrics, currentOccupied
      )
      const baseLeft = rect.left - getElementTranslateOffset(el).x
      const baseTop = rect.top - getElementTranslateOffset(el).y
      snapshot[key] = { x: free.x - baseLeft, y: free.y - baseTop }
      Object.entries(snapshot).forEach(([k, v]) => { dropOverlay[k] = v })
    }
  })
}

export function clearDropOverlay(key: string): void {
  delete dropOverlay[key]
}

export function getDropOverlayStyle(key: string): string {
  const p = dropOverlay[key]
  return p ? `translate(${p.x}px, ${p.y}px)` : ''
}
