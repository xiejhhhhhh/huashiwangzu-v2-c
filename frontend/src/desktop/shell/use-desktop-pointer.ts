import { onMounted, onUnmounted } from 'vue'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import { startBoxSelection, updateBoxSelection, endBoxSelection, selectionRect } from '@/desktop/selection/selection-box-state'
import { clearSelection, setSelection } from '@/desktop/selection/desktop-selection-state'
import { updateDragOffset, enterFolder, leaveFolder, endDrag, dragState, setDragCopyMode } from '@/desktop/drag-drop/drag-state'
import { clampIconPosition, commitDropOverlayBatch } from '@/desktop/drag-drop/drag-tool'
import { openAppById } from '@/desktop/app-registry/app-opener'

function hitTestSelection(sel: { x: number; y: number; w: number; h: number }, e: MouseEvent) {
  const ids: string[] = []
  document.querySelectorAll('.desktop-icon-item').forEach(el => {
    const r = el.getBoundingClientRect()
    const overlaps = !(r.right < sel.x || r.left > sel.x + sel.w || r.bottom < sel.y || r.top > sel.y + sel.h)
    const key = overlaps ? el.getAttribute('data-selection-key') : null
    if (key) ids.push(key)
  })
  setSelection(ids, e.ctrlKey)
}

/** Spring-loading: hover a folder long enough while dragging to open it. */
const SPRING_LOAD_MS = 800
let springTimer: ReturnType<typeof setTimeout> | null = null
let springTargetId: string | null = null

function clearSpringLoad() {
  if (springTimer) {
    clearTimeout(springTimer)
    springTimer = null
  }
  springTargetId = null
}

function scheduleSpringLoad(folderId: string) {
  if (springTargetId === folderId) return
  clearSpringLoad()
  springTargetId = folderId
  springTimer = setTimeout(() => {
    springTimer = null
    const idNum = Number(folderId)
    if (!Number.isFinite(idNum)) return
    // Prefer navigating an already open Finder window under pointer; fallback open/focus window.
    const under = document.elementFromPoint(
      // last known pointer approx: use drag ghost position origin
      dragState.originX,
      dragState.originY,
    )
    const fm = under?.closest?.('.desktop-file-manager') as HTMLElement | null
    if (fm) {
      // dispatch a soft navigation event the finder window listens via refresh path
      // openAppById reuses same folder window when allowMultiple+same folderId
      openAppById('desktop', { folderId: idNum, folderName: '文件夹' })
      return
    }
    openAppById('desktop', { folderId: idNum, folderName: '文件夹' })
  }, SPRING_LOAD_MS)
}

function detectHoveredFolder(e: MouseEvent) {
  const el = document.elementFromPoint(e.clientX, e.clientY)
  const folder = el?.closest?.('[data-folder]') as HTMLElement | null
  if (!folder) {
    leaveFolder()
    clearSpringLoad()
    return
  }
  const id = folder.getAttribute('data-folder')
  if (!id) {
    leaveFolder()
    clearSpringLoad()
    return
  }
  // Don't highlight when hovering the item being dragged
  if (dragState.draggedIds.some(did => did.endsWith(`:${id}`))) {
    leaveFolder()
    clearSpringLoad()
    return
  }
  enterFolder(id)
  if (dragState.isDragging) scheduleSpringLoad(id)
  else clearSpringLoad()
}

function snapDraggedIcons(e: MouseEvent) {
  const primaryKey = dragState.draggedIds[0]
  if (!primaryKey) return
  const dropX = dragState.originLeft + e.clientX - dragState.originX
  const dropY = dragState.originTop + e.clientY - dragState.originY
  const { x, y } = clampIconPosition(dropX, dropY)
  const offsets = commitDropOverlayBatch(primaryKey, x, y, dragState.draggedIds, dragState.offsetList)
  dragState.offsetList.forEach(({ id }) => {
    const el = document.querySelector(`[data-selection-key="${id}"]`) as HTMLElement | null
    if (!el) return
    const offset = offsets[id]
    if (offset) el.style.transform = `translate(${offset.x}px, ${offset.y}px)`
  })
}

function isDesktopSource(): boolean {
  return dragState.draggedIds.some(id => {
    const el = document.querySelector(`[data-selection-key="${id}"]`)
    return el?.closest('.desktop-icon-grid') !== null
  })
}

function getSourceFolderId(key: string): number | null {
  const el = document.querySelector(`[data-selection-key="${key}"]`)
  if (!el) return null
  const fm = el.closest('.desktop-file-manager') as HTMLElement | null
  if (fm) {
    const attr = fm.getAttribute('data-folder')
    return attr !== null ? Number(attr) : 0
  }
  return 0
}

export function useDesktopPointer() {
  const { emit } = useDesktopEventBus()

  function handleDesktopMouseDown(e: MouseEvent) {
    const target = e.target as HTMLElement | null
    if (target?.closest('.desktop-icon-item, .desktop-window, .mac-menu-bar, .mac-dock, .v40-ctx-menu, .v40-ctx-sub')) return
    if (!e.ctrlKey && !e.metaKey) clearSelection()
    startBoxSelection(e.clientX, e.clientY)
  }

  function handleDesktopMouseMove(e: MouseEvent) {
    if (dragState.isDragging) {
      // Option/Alt toggles copy while dragging (Finder-like)
      setDragCopyMode(Boolean(e.altKey))
      updateDragOffset(e.clientX - dragState.originX, e.clientY - dragState.originY)
      detectHoveredFolder(e)
      return
    }
    if (!selectionRect.value.w && !selectionRect.value.h) return
    updateBoxSelection(e.clientX, e.clientY)
    const sel = selectionRect.value
    if (sel.w >= 4 || sel.h >= 4) hitTestSelection(sel, e)
  }

  function handleDesktopMouseUp(e: MouseEvent) {
    if (dragState.isDragging) {
      clearSpringLoad()
      setDragCopyMode(Boolean(e.altKey))
      const copy = Boolean(e.altKey || dragState.copyMode)
      const el = document.elementFromPoint(e.clientX, e.clientY)
      const folderEl = el?.closest?.('[data-folder]') as HTMLElement | null
      if (folderEl) {
        const targetId = folderEl.getAttribute('data-folder')
        const srcFolderId = getSourceFolderId(dragState.draggedIds[0])
        if (srcFolderId !== null && String(srcFolderId) === targetId && !copy) {
          endDrag()
        } else {
          emit('desktop:move-to-folder', { ids: dragState.draggedIds, targetFolderId: targetId, copy })
          endDrag({ keepTransform: !copy })
        }
      } else if (isDesktopSource() && !copy) {
        snapDraggedIcons(e)
        endDrag()
      } else {
        emit('desktop:move-to-folder', { ids: dragState.draggedIds, targetFolderId: null, copy })
        endDrag()
      }
      return
    }
    endBoxSelection()
  }

  onMounted(() => {
    window.addEventListener('mousemove', handleDesktopMouseMove)
    window.addEventListener('mouseup', handleDesktopMouseUp)
  })
  onUnmounted(() => {
    clearSpringLoad()
    window.removeEventListener('mousemove', handleDesktopMouseMove)
    window.removeEventListener('mouseup', handleDesktopMouseUp)
  })
  return { handleDesktopMouseDown }
}
