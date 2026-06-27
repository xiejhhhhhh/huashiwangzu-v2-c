import { onUnmounted, ref, type Ref } from 'vue'

type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
type InteractionConfig = {
  id: string; x: number; y: number; width: number; height: number; maximized: boolean
  minWidth: number; minHeight: number; rootEl: Ref<HTMLElement | null>
  activate: (id: string) => void; updatePosition: (id: string, x: number, y: number) => void
  updateGeometry: (id: string, x: number, y: number, width: number, height: number) => void
}

const resizeDirections: ResizeDirection[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

export function useWindowInteraction(readConfig: () => InteractionConfig) {
  const dragging = ref(false)
  const dragStart = ref({ x: 0, y: 0, winX: 0, winY: 0 })
  const resizeInfo = ref<{ direction: ResizeDirection; startX: number; startY: number; initialX: number; initialY: number; initialWidth: number; initialHeight: number } | null>(null)
  const getBounds = () => {
    const parent = readConfig().rootEl.value?.parentElement
    return { containerWidth: parent?.clientWidth ?? window.innerWidth, availableHeight: (parent?.clientHeight ?? window.innerHeight) - 48 }
  }
  function startDrag(e: MouseEvent) {
    const cfg = readConfig(); if (cfg.maximized) return
    cfg.activate(cfg.id); dragging.value = true
    dragStart.value = { x: e.clientX, y: e.clientY, winX: cfg.x, winY: cfg.y }
    document.addEventListener('mousemove', handleDragMove); document.addEventListener('mouseup', stopInteraction)
  }
  function handleDragMove(e: MouseEvent) {
    if (!dragging.value) return
    const cfg = readConfig(), { containerWidth, availableHeight } = getBounds(), dx = e.clientX - dragStart.value.x, dy = e.clientY - dragStart.value.y
    cfg.updatePosition(cfg.id, Math.max(0, Math.min(dragStart.value.winX + dx, containerWidth - cfg.width)), Math.max(0, Math.min(dragStart.value.winY + dy, availableHeight - cfg.height)))
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
    dragging.value = false; resizeInfo.value = null
    document.removeEventListener('mousemove', handleDragMove); document.removeEventListener('mousemove', handleResizeMove); document.removeEventListener('mouseup', stopInteraction)
  }
  onUnmounted(stopInteraction)
  return { resizeDirections, startDrag, startResize }
}
