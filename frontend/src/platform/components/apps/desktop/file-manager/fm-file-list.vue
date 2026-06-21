<template>
  <section class="fm-file-list" :class="`fm-view-${viewMode}`">
    <!-- Column headers (list view only) -->
    <div v-if="viewMode === 'list'" class="fm-list-header">
      <span class="fm-col-icon"></span>
      <button class="fm-col-name" @click="$emit('sort', 'name')">
        名称 <span v-if="sortColumn === 'name'">{{ sortDirection === 'asc' ? '↑' : '↓' }}</span>
      </button>
      <button class="fm-col-date" @click="$emit('sort', 'date')">
        修改日期 <span v-if="sortColumn === 'date'">{{ sortDirection === 'asc' ? '↑' : '↓' }}</span>
      </button>
      <button class="fm-col-type" @click="$emit('sort', 'type')">
        类型 <span v-if="sortColumn === 'type'">{{ sortDirection === 'asc' ? '↑' : '↓' }}</span>
      </button>
      <button class="fm-col-size" @click="$emit('sort', 'size')">
        大小 <span v-if="sortColumn === 'size'">{{ sortDirection === 'asc' ? '↑' : '↓' }}</span>
      </button>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="fm-state">加载中...</div>

    <!-- Empty state -->
    <div v-else-if="items.length === 0" class="fm-state">这个文件夹是空的</div>

    <!-- File entries -->
    <template v-else>
      <div v-if="viewMode === 'grid'" class="fm-content-grid">
        <button
          v-for="item in items"
          :key="`${item.is_folder ? 'folder' : 'file'}-${item.id}`"
          :draggable="false"
          class="fm-entry"
          :data-fm-entry-id="item.id"
          :data-fm-entry-kind="item.is_folder ? 'folder' : 'file'"
          :class="{ 'fm-entry-selected': selectedId === item.id, 'fm-entry-drag-over': item.is_folder && dragOverId === item.id }"
          type="button"
          @click="handleClick(item, $event)"
          @dblclick="handleDoubleClick(item, $event)"
          @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
          @pointerdown="onPointerDown(item, $event)"
          @mousedown="onMouseDown(item, $event)"
        >
          <FileVisualIcon :kind="item.is_folder || !item.format ? 'folder' : 'file'" :extension="item.format || ''" :size="42" />
          <span class="fm-entry-name">{{ displayName(item) }}</span>
        </button>
      </div>

      <div v-else class="fm-content-list">
        <button
          v-for="item in items"
          :key="`${item.is_folder ? 'folder' : 'file'}-${item.id}`"
          :draggable="false"
          class="fm-entry"
          :data-fm-entry-id="item.id"
          :data-fm-entry-kind="item.is_folder ? 'folder' : 'file'"
          :class="{ 'fm-entry-selected': selectedId === item.id, 'fm-entry-drag-over': item.is_folder && dragOverId === item.id }"
          type="button"
          @click="handleClick(item, $event)"
          @dblclick="handleDoubleClick(item, $event)"
          @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
          @pointerdown="onPointerDown(item, $event)"
          @mousedown="onMouseDown(item, $event)"
        >
          <FileVisualIcon :kind="item.is_folder || !item.format ? 'folder' : 'file'" :extension="item.format || ''" :size="22" />
          <span class="fm-entry-name">{{ displayName(item) }}</span>
          <span class="fm-entry-date">{{ item.created_at?.slice(0, 10) || '' }}</span>
          <span class="fm-entry-kind">{{ item.is_folder ? '文件夹' : (item.format || '文件') }}</span>
          <span class="fm-entry-size">{{ item.is_folder ? '' : formatSize(item.file_size) }}</span>
        </button>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import type { FileEntry } from '@/shared/api/types'

const dragSource = ref<FileEntry | null>(null)
const dragOverId = ref<number | null>(null)
const dragNavOverEl = ref<Element | null>(null)
const pointerSource = ref<FileEntry | null>(null)
const pointerStart = ref<{ x: number; y: number } | null>(null)
const pointerDragging = ref(false)
const mouseSource = ref<FileEntry | null>(null)
const mouseStart = ref<{ x: number; y: number } | null>(null)
const mouseDragging = ref(false)
let suppressNextClick = false
let lastDropKey = ''
let lastDropAt = 0

// ── Pointer-based drag (primary, works on :draggable="false" entries) ──

function onMouseDown(item: FileEntry, e: MouseEvent) {
  if (e.button !== 0) return
  mouseSource.value = item
  mouseStart.value = { x: e.clientX, y: e.clientY }
  mouseDragging.value = false
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onPointerDown(item: FileEntry, e: PointerEvent) {
  if (e.button !== 0) return
  pointerSource.value = item
  pointerStart.value = { x: e.clientX, y: e.clientY }
  pointerDragging.value = false
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function onPointerMove(e: PointerEvent) {
  const source = pointerSource.value
  const start = pointerStart.value
  if (!source || !start) return

  const dx = e.clientX - start.x
  const dy = e.clientY - start.y
  if (!pointerDragging.value && Math.hypot(dx, dy) < 6) return

  pointerDragging.value = true
  e.preventDefault()
  const target = findDropTarget(e.clientX, e.clientY)
  // 文件夹落点
  if (target?.kind === 'folder') {
    dragOverId.value = target.folder.id !== source.id ? target.folder.id : null
  } else {
    dragOverId.value = null
  }
  // 导航落点高亮
  if (target?.kind === 'nav' && target.el) {
    if (dragNavOverEl.value !== target.el) {
      clearNavOver()
      target.el.classList.add('nav-drop-over')
      dragNavOverEl.value = target.el
    }
  } else {
    clearNavOver()
  }
}

function onPointerUp(e: PointerEvent) {
  const source = pointerSource.value
  const target = pointerDragging.value ? findDropTarget(e.clientX, e.clientY) : null
  const didDrag = pointerDragging.value
  resetPointerDrag()

  if (!didDrag) return
  suppressNextClick = true
  window.setTimeout(() => { suppressNextClick = false }, 0)
  if (!source) return
  if (target?.kind === 'folder') {
    if (target.folder.id === source.id) return
    emitDragOnce(source, target.folder, 'drag-move')
  } else if (target?.kind === 'nav') {
    emitDragOnce(source, { targetFolderId: target.folderId }, 'drag-move-to')
  }
}

function onMouseMove(e: MouseEvent) {
  const source = mouseSource.value
  const start = mouseStart.value
  if (!source || !start) return

  const dx = e.clientX - start.x
  const dy = e.clientY - start.y
  if (!mouseDragging.value && Math.hypot(dx, dy) < 6) return

  mouseDragging.value = true
  e.preventDefault()
  const target = findDropTarget(e.clientX, e.clientY)
  if (target?.kind === 'folder') {
    dragOverId.value = target.folder.id !== source.id ? target.folder.id : null
  } else {
    dragOverId.value = null
  }
  if (target?.kind === 'nav' && target.el) {
    if (dragNavOverEl.value !== target.el) {
      clearNavOver()
      target.el.classList.add('nav-drop-over')
      dragNavOverEl.value = target.el
    }
  } else {
    clearNavOver()
  }
}

function onMouseUp(e: MouseEvent) {
  const source = mouseSource.value
  const target = mouseDragging.value ? findDropTarget(e.clientX, e.clientY) : null
  const didDrag = mouseDragging.value
  resetMouseDrag()

  if (!didDrag) return
  suppressNextClick = true
  window.setTimeout(() => { suppressNextClick = false }, 0)
  if (!source) return
  if (target?.kind === 'folder') {
    if (target.folder.id === source.id) return
    emitDragOnce(source, target.folder, 'drag-move')
  } else if (target?.kind === 'nav') {
    emitDragOnce(source, { targetFolderId: target.folderId }, 'drag-move-to')
  }
}

type DragTarget =
  | { kind: 'folder'; folder: FileEntry }
  | { kind: 'nav'; folderId: number | null; el: Element }
  | null

function findDropTarget(x: number, y: number): DragTarget {
  const element = document.elementFromPoint(x, y)
  if (!element) return null
  // 先看是否为导航落点
  const navEl = element.closest('[data-fm-navdrop]')
  if (navEl instanceof Element) {
    const kind = navEl.getAttribute('data-fm-navdrop')
    if (kind === 'root') return { kind: 'nav', folderId: null, el: navEl }
    if (kind === 'folder') {
      const raw = navEl.getAttribute('data-fm-folder-id') || ''
      const folderId = raw ? Number(raw) : null
      if (folderId === null || (folderId !== null && Number.isFinite(folderId))) {
        return { kind: 'nav', folderId: folderId, el: navEl }
      }
    }
    return null
  }
  // 再走原来的文件夹条目识别
  const entry = element.closest('[data-fm-entry-id]')
  if (!entry) return null
  if (entry.getAttribute('data-fm-entry-kind') !== 'folder') return null
  const rawId = entry.getAttribute('data-fm-entry-id')
  if (!rawId) return null
  const id = Number(rawId)
  if (!Number.isFinite(id)) return null
  const folder = props.items.find(item => item.id === id && item.is_folder)
  return folder ? { kind: 'folder', folder } : null
}

function clearNavOver() {
  if (dragNavOverEl.value) {
    dragNavOverEl.value.classList.remove('nav-drop-over')
    dragNavOverEl.value = null
  }
}

function emitDragOnce(
  source: FileEntry,
  target: FileEntry | { targetFolderId: number | null },
  eventType: 'drag-move' | 'drag-move-to',
) {
  const targetId = target instanceof Object && 'targetFolderId' in target ? target.targetFolderId : (target as FileEntry).id
  const key = `${source.is_folder ? 'folder' : 'file'}:${source.id}->${String(targetId)}`
  const now = Date.now()
  if (key === lastDropKey && now - lastDropAt < 800) return
  lastDropKey = key
  lastDropAt = now
  if (eventType === 'drag-move' && 'id' in target) {
    emit('drag-move', source, target as FileEntry)
  } else if (eventType === 'drag-move-to') {
    emit('drag-move-to', source, (target as { targetFolderId: number | null }).targetFolderId)
  }
}

function resetPointerDrag() {
  pointerSource.value = null
  pointerStart.value = null
  pointerDragging.value = false
  dragOverId.value = null
  clearNavOver()
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

function resetMouseDrag() {
  mouseSource.value = null
  mouseStart.value = null
  mouseDragging.value = false
  dragOverId.value = null
  clearNavOver()
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

const props = defineProps<{
  items: FileEntry[]
  selectedId: number | null
  viewMode: 'grid' | 'list'
  loading: boolean
  displayName: (file: FileEntry) => string
  formatSize: (size: number) => string
  sortColumn: 'name' | 'date' | 'type' | 'size'
  sortDirection: 'asc' | 'desc'
}>()

function handleClick(item: FileEntry, e: MouseEvent) {
  if (suppressNextClick) {
    e.preventDefault()
    e.stopPropagation()
    suppressNextClick = false
    return
  }
  emit('select', item)
}

function handleDoubleClick(item: FileEntry, e: MouseEvent) {
  if (suppressNextClick) {
    e.preventDefault()
    e.stopPropagation()
    suppressNextClick = false
    return
  }
  emit('open', item)
}

onBeforeUnmount(() => {
  resetPointerDrag()
  resetMouseDrag()
})

const emit = defineEmits<{
  (e: 'select', item: FileEntry): void
  (e: 'open', item: FileEntry): void
  (e: 'context-menu', item: FileEntry, event: MouseEvent): void
  (e: 'sort', column: string): void
  (e: 'drag-move', source: FileEntry, targetFolder: FileEntry): void
  (e: 'drag-move-to', source: FileEntry, targetFolderId: number | null): void
}>()
</script>

<style scoped>
.fm-file-list {
  min-height: 0;
  overflow: auto;
  background:
    linear-gradient(90deg, rgba(203, 213, 225, 0.2) 1px, transparent 1px),
    linear-gradient(180deg, rgba(203, 213, 225, 0.2) 1px, transparent 1px),
    #f8fafc;
  background-size: 92px 92px;
}

.fm-view-list {
  display: flex;
  flex-direction: column;
}

.fm-list-header {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 140px 92px 80px;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  height: 30px;
  border-bottom: 1px solid #dbe4ee;
  background: #f1f5f9;
  position: sticky;
  top: 0;
  z-index: 1;
}

.fm-list-header button {
  border: none;
  background: transparent;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  text-align: left;
  padding: 0 4px;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}
.fm-list-header button:hover {
  color: #334155;
}

.fm-col-icon {
  pointer-events: none;
}

.fm-content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
  align-content: start;
  gap: 10px;
  padding: 16px;
}

.fm-content-list {
  display: grid;
  align-content: start;
  gap: 4px;
  padding: 4px 0;
}

.fm-content-list .fm-entry {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 140px 92px 80px;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
}

.fm-entry {
  min-width: 0;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #243244;
  cursor: pointer;
  user-select: none;
  text-align: left;
}

.fm-content-grid .fm-entry {
  height: 104px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  padding: 8px 6px;
}

.fm-entry:hover,
.fm-entry-selected {
  background: rgba(219, 234, 254, 0.82);
  border-color: rgba(96, 165, 250, 0.56);
}

.fm-entry-name {
  max-width: 100%;
  font-size: 12px;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fm-content-grid .fm-entry-name {
  text-align: center;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.fm-content-list .fm-entry-name {
  text-align: left;
  white-space: nowrap;
}

.fm-entry-date {
  color: #64748b;
  font-size: 12px;
}

.fm-entry-kind,
.fm-entry-size {
  color: #64748b;
  font-size: 12px;
  text-align: right;
}

.fm-state {
  min-height: 100%;
  display: grid;
  place-items: center;
  color: #64748b;
  font-size: 13px;
  padding: 40px;
}

.fm-entry-drag-over {
  background: rgba(59, 130, 246, 0.18) !important;
  border-color: rgba(59, 130, 246, 0.65) !important;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
}
</style>
