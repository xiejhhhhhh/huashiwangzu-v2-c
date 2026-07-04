import { onUnmounted, ref, type Ref } from 'vue'

type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
type SnapKind = 'left' | 'right' | 'top'
type WindowGeometry = { x: number; y: number; width: number; height: number }
export type SnapPreview = { kind: SnapKind; x: number; y: number; width: number; height: number }
type InteractionConfig = {
  id: string; x: number; y: number; width: number; height: number; maximized: boolean
  minWidth: number; minHeight: number; rootEl: Ref<HTMLElement | null>
  activate: (id: string) => void; updatePosition: (id: string, x: number, y: number) => void
  updateGeometry: (id: string, x: number, y: number, width: number, height: number) => void
  maximize: (id: string, restoreState?: WindowGeometry) => void
}

const resizeDirections: ResizeDirection[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
const SNAP_EDGE_SIZE = 28
const TASKBAR_RESERVED_HEIGHT = 48

function clampDimension(value: number, min: number, max: number): number {
  if (max <= 0) return 0
  if (max < min) return max
  return Math.max(min, Math.min(value, max))
}

export function useWindowInteraction(readConfig: () => InteractionConfig) {
  const dragging = ref(false)
  const snapPreview = ref<SnapPreview | null>(null)
  const dragStart = ref({ x: 0, y: 0, winX: 0, winY: 0, winWidth: 0, winHeight: 0 })
  const resizeInfo = ref<{ direction: ResizeDirection; startX: number; startY: number; initialX: number; initialY: number; initialWidth: number; initialHeight: number } | null>(null)
  const getBounds = () => {
    const parent = readConfig().rootEl.value?.parentElement
    const rect = parent?.getBoundingClientRect()
    const containerWidth = parent?.clientWidth ?? window.innerWidth
    const containerHeight = parent?.clientHeight ?? window.innerHeight
    return {
      containerLeft: rect?.left ?? 0,
      containerTop: rect?.top ?? 0,
      containerWidth,
      availableHeight: Math.max(0, containerHeight - TASKBAR_RESERVED_HEIGHT),
    }
  }
  function resolveSnapPreview(e: MouseEvent): SnapPreview | null {
    const cfg = readConfig()
    const { containerLeft, containerTop, containerWidth, availableHeight } = getBounds()
    const pointerX = e.clientX - containerLeft
    const pointerY = e.clientY - containerTop
    if (pointerY <= SNAP_EDGE_SIZE) {
      return { kind: 'top', x: 0, y: 0, width: containerWidth, height: availableHeight }
    }
    const halfWidth = clampDimension(Math.round(containerWidth / 2), cfg.minWidth, containerWidth)
    const snapHeight = clampDimension(availableHeight, cfg.minHeight, availableHeight)
    if (pointerX <= SNAP_EDGE_SIZE) {
      return { kind: 'left', x: 0, y: 0, width: halfWidth, height: snapHeight }
    }
    if (pointerX >= containerWidth - SNAP_EDGE_SIZE) {
      return { kind: 'right', x: Math.max(0, containerWidth - halfWidth), y: 0, width: halfWidth, height: snapHeight }
    }
    return null
  }
  function startDrag(e: MouseEvent) {
    const cfg = readConfig(); if (cfg.maximized) return
    cfg.activate(cfg.id); dragging.value = true
    snapPreview.value = null
    dragStart.value = { x: e.clientX, y: e.clientY, winX: cfg.x, winY: cfg.y, winWidth: cfg.width, winHeight: cfg.height }
    document.addEventListener('mousemove', handleDragMove); document.addEventListener('mouseup', stopInteraction)
  }
  function handleDragMove(e: MouseEvent) {
    if (!dragging.value) return
    const cfg = readConfig(), { containerWidth, availableHeight } = getBounds(), dx = e.clientX - dragStart.value.x, dy = e.clientY - dragStart.value.y
    cfg.updatePosition(cfg.id, Math.max(0, Math.min(dragStart.value.winX + dx, Math.max(0, containerWidth - cfg.width))), Math.max(0, Math.min(dragStart.value.winY + dy, Math.max(0, availableHeight - cfg.height))))
    snapPreview.value = resolveSnapPreview(e)
  }
  function startResize(direction: ResizeDirection, e: MouseEvent) {
    const cfg = readConfig(); if (cfg.maximized) return
    cfg.activate(cfg.id)
    resizeInfo.value = { direction, startX: e.clientX, startY: e.clientY, initialX: cfg.x, initialY: cfg.y, initialWidth: cfg.width, initialHeight: cfg.height }
    document.addEventListener('mousemove', handleResizeMove); document.addEventListener('mouseup', stopInteraction)
  }
  function handleResizeMove(e: MouseEvent) {
    if (!resizeInfo.value) return
    const cfg = readConfig(), info = resizeInfo.value, { containerWidth, availableHeight } = getBounds(), dx = e.clientX - info.startX, dy = e.clientY - info.startY
    let { initialX: x, initialY: y, initialWidth: width, initialHeight: height } = info
    if (info.direction.includes('e')) width = clampDimension(info.initialWidth + dx, cfg.minWidth, containerWidth - info.initialX)
    if (info.direction.includes('s')) height = clampDimension(info.initialHeight + dy, cfg.minHeight, availableHeight - info.initialY)
    if (info.direction.includes('w')) {
      const rightEdge = info.initialX + info.initialWidth
      const nextX = Math.max(0, Math.min(info.initialX + dx, rightEdge))
      width = clampDimension(rightEdge - nextX, cfg.minWidth, rightEdge)
      x = rightEdge - width
    }
    if (info.direction.includes('n')) {
      const bottomEdge = info.initialY + info.initialHeight
      const nextY = Math.max(0, Math.min(info.initialY + dy, bottomEdge))
      height = clampDimension(bottomEdge - nextY, cfg.minHeight, bottomEdge)
      y = bottomEdge - height
    }
    cfg.updateGeometry(cfg.id, Math.round(x), Math.round(y), Math.round(width), Math.round(height))
  }
  function stopInteraction(e?: MouseEvent) {
    const preview = dragging.value && e ? resolveSnapPreview(e) : snapPreview.value
    if (dragging.value && preview) {
      const cfg = readConfig()
      if (preview.kind === 'top') {
        cfg.maximize(cfg.id, {
          x: dragStart.value.winX,
          y: dragStart.value.winY,
          width: dragStart.value.winWidth,
          height: dragStart.value.winHeight,
        })
      } else {
        cfg.updateGeometry(cfg.id, preview.x, preview.y, preview.width, preview.height)
      }
    }
    dragging.value = false; resizeInfo.value = null
    snapPreview.value = null
    document.removeEventListener('mousemove', handleDragMove); document.removeEventListener('mousemove', handleResizeMove); document.removeEventListener('mouseup', stopInteraction)
  }
  onUnmounted(stopInteraction)
  return { resizeDirections, snapPreview, dragging, startDrag, startResize }
}
