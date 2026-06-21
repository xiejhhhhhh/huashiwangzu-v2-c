import { onMounted, onUnmounted } from 'vue'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import { startBoxSelection, updateBoxSelection, endBoxSelection, selectionRect } from '@/desktop/selection/selection-box-state'
import { clearSelection, setSelection } from '@/desktop/selection/desktop-selection-state'
import { updateDragOffset, enterFolder, leaveFolder, endDrag, dragState } from '@/desktop/drag-drop/drag-state'
import { clampIconPosition, commitDropOverlayBatch } from '@/desktop/drag-drop/drag-tool'

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

function detectHoveredFolder(e: MouseEvent) {
  const el = document.elementFromPoint(e.clientX, e.clientY)
  const folder = el?.closest?.('[data-folder]') as HTMLElement | null
  if (!folder) { leaveFolder(); return }
  const id = folder.getAttribute('data-folder')
  if (!id) { leaveFolder(); return }
  // Don't highlight when hovering the item being dragged
  if (dragState.draggedIds.some(did => did.endsWith(`:${id}`))) { leaveFolder(); return }
  enterFolder(id)
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
    if (e.target !== e.currentTarget) return
    if (!e.ctrlKey) clearSelection()
    startBoxSelection(e.clientX, e.clientY)
  }

  function handleDesktopMouseMove(e: MouseEvent) {
    if (dragState.isDragging) {
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
      const el = document.elementFromPoint(e.clientX, e.clientY)
      const folderEl = el?.closest?.('[data-folder]') as HTMLElement | null
      if (folderEl) {
        const targetId = folderEl.getAttribute('data-folder')
        const srcFolderId = getSourceFolderId(dragState.draggedIds[0])
        if (srcFolderId !== null && String(srcFolderId) === targetId) {
          endDrag()
        } else {
          emit('desktop:move-to-folder', { ids: dragState.draggedIds, targetFolderId: targetId })
          endDrag({ keepTransform: true })
        }
      } else if (isDesktopSource()) {
        snapDraggedIcons(e)
        endDrag()
      } else {
        emit('desktop:move-to-folder', { ids: dragState.draggedIds, targetFolderId: null })
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
    window.removeEventListener('mousemove', handleDesktopMouseMove)
    window.removeEventListener('mouseup', handleDesktopMouseUp)
  })
  return { handleDesktopMouseDown }
}
