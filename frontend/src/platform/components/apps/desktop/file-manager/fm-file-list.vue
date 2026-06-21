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
          :data-selection-key="(item.is_folder ? 'folder' : 'file') + ':' + item.id"
          :data-folder="item.is_folder ? String(item.id) : undefined"
          :class="{ 'fm-entry-selected': selectedId === item.id }"
          type="button"
          @click="handleClick(item, $event)"
          @dblclick="handleDoubleClick(item, $event)"
          @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
          @mousedown.stop="handleEntryMouseDown(item, $event)"
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
          :data-selection-key="(item.is_folder ? 'folder' : 'file') + ':' + item.id"
          :data-folder="item.is_folder ? String(item.id) : undefined"
          :class="{ 'fm-entry-selected': selectedId === item.id }"
          type="button"
          @click="handleClick(item, $event)"
          @dblclick="handleDoubleClick(item, $event)"
          @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
          @mousedown.stop="handleEntryMouseDown(item, $event)"
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
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import type { FileEntry } from '@/shared/api/types'
import { startDrag } from '@/desktop/drag-drop/drag-state'

let suppressNextClick = false
let pendingDrag: { key: string; startX: number; startY: number } | null = null

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

function handleEntryMouseDown(item: FileEntry, e: MouseEvent) {
  if (e.button !== 0) return
  pendingDrag = {
    key: (item.is_folder ? 'folder' : 'file') + ':' + item.id,
    startX: e.clientX,
    startY: e.clientY,
  }
  document.addEventListener('mousemove', handlePendingDragMove)
  document.addEventListener('mouseup', clearPendingDrag)
}

function handlePendingDragMove(e: MouseEvent) {
  if (!pendingDrag) return
  const dx = e.clientX - pendingDrag.startX
  const dy = e.clientY - pendingDrag.startY
  if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return
  suppressNextClick = true
  startDrag([pendingDrag.key], pendingDrag.startX, pendingDrag.startY)
  clearPendingDrag()
}

function clearPendingDrag() {
  document.removeEventListener('mousemove', handlePendingDragMove)
  document.removeEventListener('mouseup', clearPendingDrag)
  pendingDrag = null
}

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

const emit = defineEmits<{
  (e: 'select', item: FileEntry): void
  (e: 'open', item: FileEntry): void
  (e: 'context-menu', item: FileEntry, event: MouseEvent): void
  (e: 'sort', column: string): void
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
</style>
