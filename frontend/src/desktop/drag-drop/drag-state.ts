import { reactive } from 'vue'
import { createDragGhost, updateDragGhostPosition, removeDragGhost } from './drag-ghost'

interface DragState {
  isDragging: boolean
  draggedIds: string[]
  dragOverId: string | null
  originX: number
  originY: number
  originLeft: number
  originTop: number
  grabOffsetX: number
  grabOffsetY: number
  offsetList: { id: string; dx: number; dy: number; baseLeft: number; baseTop: number }[]
}

const dragState = reactive<DragState>({
  isDragging: false,
  draggedIds: [],
  dragOverId: null,
  originX: 0, originY: 0,
  originLeft: 0, originTop: 0,
  grabOffsetX: 0, grabOffsetY: 0,
  offsetList: [],
})

function getTranslateOffset(el: Element): { x: number; y: number } {
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

export function startDrag(ids: string[], x: number, y: number): void {
  dragState.isDragging = true
  dragState.draggedIds = ids
  dragState.originX = x
  dragState.originY = y
  const primaryEl = document.querySelector(`[data-selection-key="${ids[0]}"]`)
  const primaryRect = primaryEl?.getBoundingClientRect()
  if (!primaryRect) { endDrag(); return }
  dragState.originLeft = primaryRect.left
  dragState.originTop = primaryRect.top
  dragState.grabOffsetX = x - primaryRect.left
  dragState.grabOffsetY = y - primaryRect.top
  dragState.offsetList = ids.map(id => {
    const el = document.querySelector(`[data-selection-key="${id}"]`)
    const r = el?.getBoundingClientRect()
    const offset = el ? getTranslateOffset(el) : { x: 0, y: 0 }
    return {
      id,
      dx: (r?.left ?? 0) - primaryRect.left,
      dy: (r?.top ?? 0) - primaryRect.top,
      baseLeft: (r?.left ?? 0) - offset.x,
      baseTop: (r?.top ?? 0) - offset.y,
    }
  })
  document.body.classList.add('desktop-dragging')

  ids.forEach(id => {
    const el = document.querySelector(`[data-selection-key="${id}"]`) as HTMLElement | null
    if (!el) return
    el.style.opacity = '0.4'
    el.style.pointerEvents = 'none'
  })

  createDragGhost(ids, x, y, dragState.grabOffsetX, dragState.grabOffsetY)
}

export function updateDragOffset(dx: number, dy: number): void {
  if (!dragState.isDragging) return
  updateDragGhostPosition(dragState.originX + dx, dragState.originY + dy, dragState.grabOffsetX, dragState.grabOffsetY)
}

export function enterFolder(id: string): void {
  dragState.dragOverId = id
}

export function leaveFolder(): void {
  dragState.dragOverId = null
}

export function endDrag(options: { keepTransform?: boolean } = {}): void {
  const draggedIds = new Set(dragState.draggedIds)
  dragState.isDragging = false
  dragState.draggedIds = []
  dragState.dragOverId = null
  dragState.offsetList = []
  document.body.classList.remove('desktop-dragging')
  removeDragGhost()
  document.querySelectorAll('[data-selection-key]').forEach(el => {
    (el as HTMLElement).style.position = ''
    ;(el as HTMLElement).style.left = ''
    ;(el as HTMLElement).style.top = ''
    ;(el as HTMLElement).style.zIndex = ''
    ;(el as HTMLElement).style.pointerEvents = ''
    ;(el as HTMLElement).style.transition = ''
    ;(el as HTMLElement).style.opacity = ''
    if (!options.keepTransform && draggedIds.has(el.getAttribute('data-selection-key') || '')) {
      ;(el as HTMLElement).style.transform = ''
    }
  })
}

export { dragState }
