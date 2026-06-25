import { computed, onUnmounted, ref, type Ref } from 'vue'

type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
export type SnapZone = 'left' | 'right' | 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'maximize' | null

type InteractionConfig = {
  id: string; x: number; y: number; width: number; height: number; maximized: boolean
  minWidth: number; minHeight: number; rootEl: Ref<HTMLElement | null>
  activate: (id: string) => void; updatePosition: (id: string, x: number, y: number) => void
  updateGeometry: (id: string, x: number, y: number, width: number, height: number) => void
  maximizeWindow: (id: string) => void
}

const SNAP_THRESHOLD = 60
const resizeDirections: ResizeDirection[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

export function useWindowInteraction(readConfig: () => InteractionConfig) {
  const dragging = ref(false)
  const dragStart = ref({ x: 0, y: 0, winX: 0, winY: 0 })
  const resizeInfo = ref<{ direction: ResizeDirection; startX: number; startY: number; initialX: number; initialY: number; initialWidth: number; initialHeight: number } | null>(null)
  const snapPreview = ref<SnapZone>(null)
  const isInteracting = computed(() => dragging.value || resizeInfo.value !== null)

  const getBounds = () => {
    const parent = readConfig().rootEl.value?.parentElement
    let taskbarHeight = 40
    if (typeof document !== 'undefined') {
      const cssVar = getComputedStyle(document.documentElement).getPropertyValue('--taskbar-height').trim()
      if (cssVar) {
        const parsed = parseInt(cssVar, 10)
        if (!isNaN(parsed)) taskbarHeight = parsed
      }
    }
    return { containerWidth: parent?.clientWidth ?? window.innerWidth, availableHeight: (parent?.clientHeight ?? window.innerHeight) - taskbarHeight }
  }

  function detectSnapZone(cfg: { x: number; y: number; width: number; height: number }): SnapZone {
    const { containerWidth, availableHeight } = getBounds()
    const nearLeft = cfg.x < SNAP_THRESHOLD
    const nearRight = cfg.x + cfg.width > containerWidth - SNAP_THRESHOLD
    const nearTop = cfg.y < SNAP_THRESHOLD
    const nearBottom = cfg.y + cfg.height > availableHeight - SNAP_THRESHOLD

    if (nearLeft && nearTop) return 'top-left'
    if (nearRight && nearTop) return 'top-right'
    if (nearLeft && nearBottom) return 'bottom-left'
    if (nearRight && nearBottom) return 'bottom-right'
    if (nearLeft) return 'left'
    if (nearRight) return 'right'
    if (nearTop) return 'maximize'
    return null
  }

  function getSnapGeometry(zone: SnapZone): { x: number; y: number; width: number; height: number } | null {
    if (!zone || zone === 'maximize') return null
    const { containerWidth, availableHeight } = getBounds()
    const halfW = Math.round(containerWidth / 2)
    const halfH = Math.round(availableHeight / 2)

    switch (zone) {
      case 'left': return { x: 0, y: 0, width: halfW, height: availableHeight }
      case 'right': return { x: halfW, y: 0, width: halfW, height: availableHeight }
      case 'top-left': return { x: 0, y: 0, width: halfW, height: halfH }
      case 'top-right': return { x: halfW, y: 0, width: halfW, height: halfH }
      case 'bottom-left': return { x: 0, y: halfH, width: halfW, height: halfH }
      case 'bottom-right': return { x: halfW, y: halfH, width: halfW, height: halfH }
      default: return null
    }
  }

  function startDrag(e: MouseEvent) {
    const cfg = readConfig(); if (cfg.maximized) return
    cfg.activate(cfg.id); dragging.value = true
    snapPreview.value = null
    dragStart.value = { x: e.clientX, y: e.clientY, winX: cfg.x, winY: cfg.y }
    document.addEventListener('mousemove', handleDragMove); document.addEventListener('mouseup', stopInteraction)
  }

  function handleDragMove(e: MouseEvent) {
    if (!dragging.value) return
    const cfg = readConfig(), { containerWidth, availableHeight } = getBounds(), dx = e.clientX - dragStart.value.x, dy = e.clientY - dragStart.value.y
    const newX = Math.max(0, Math.min(dragStart.value.winX + dx, containerWidth - cfg.width))
    const newY = Math.max(0, Math.min(dragStart.value.winY + dy, availableHeight - cfg.height))
    cfg.updatePosition(cfg.id, newX, newY)
    const updatedCfg = readConfig()
    snapPreview.value = detectSnapZone(updatedCfg)
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
    if (info.direction.includes('e')) width = Math.max(cfg.minWidth, Math.min(info.initialWidth + dx, containerWidth - info.initialX))
    if (info.direction.includes('s')) height = Math.max(cfg.minHeight, Math.min(info.initialHeight + dy, availableHeight - info.initialY))
    if (info.direction.includes('w')) { x = Math.max(0, Math.min(info.initialX + dx, info.initialX + info.initialWidth - cfg.minWidth)); width = info.initialWidth - (x - info.initialX) }
    if (info.direction.includes('n')) { y = Math.max(0, Math.min(info.initialY + dy, info.initialY + info.initialHeight - cfg.minHeight)); height = info.initialHeight - (y - info.initialY) }
    cfg.updateGeometry(cfg.id, Math.round(x), Math.round(y), Math.round(width), Math.round(height))
  }

  function stopInteraction() {
    const wasDragging = dragging.value
    const wasResizing = resizeInfo.value !== null
    const currentZone = snapPreview.value

    dragging.value = false; resizeInfo.value = null
    document.removeEventListener('mousemove', handleDragMove); document.removeEventListener('mousemove', handleResizeMove); document.removeEventListener('mouseup', stopInteraction)

    if (wasDragging && !wasResizing) {
      const cfg = readConfig()
      if (currentZone === 'maximize') {
        cfg.maximizeWindow(cfg.id)
      } else {
        const geom = getSnapGeometry(currentZone)
        if (geom) {
          cfg.updateGeometry(cfg.id, geom.x, geom.y, geom.width, geom.height)
        }
      }
    }
    snapPreview.value = null
  }

  onUnmounted(stopInteraction)
  return { resizeDirections, startDrag, startResize, dragging, snapPreview, isInteracting }
}
