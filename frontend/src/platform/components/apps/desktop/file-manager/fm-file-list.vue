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

    <LoadStateBanner
      v-if="loadStatus === 'stale'"
      class="fm-load-banner"
      :status="loadStatus"
      :error="loadError"
      stale-text="文件列表可能不是最新"
      @retry="emit('retry')"
    />

    <!-- Loading state -->
    <div v-if="loading && items.length === 0" class="fm-state">加载中...</div>

    <div v-else-if="loadStatus === 'error'" class="fm-state fm-state-error">
      <LoadStateBanner
        :status="loadStatus"
        :error="loadError"
        error-text="文件列表加载失败"
        @retry="emit('retry')"
      />
    </div>

    <!-- Empty state -->
    <MacEmptyState
      v-else-if="items.length === 0"
      class="fm-empty"
      title="这个文件夹是空的"
      description="把文件拖到这里，或从菜单新建。"
      icon="📁"
    />

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
          <FileVisualIcon :kind="item.is_folder || !item.format ? 'folder' : 'file'" :extension="item.format || ''" :size="52" />
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
import LoadStateBanner from '@/shared/components/load-state-banner.vue'
import { MacEmptyState } from '@/desktop/app-kit'
import type { ApiErrorInfo } from '@/shared/api/response-transform'
import type { LoadStatus } from '@/shared/composables/use-load-state'

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
  loadStatus: LoadStatus
  loadError: ApiErrorInfo | null
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
  (e: 'retry'): void
}>()
</script>

<style scoped>
.fm-file-list {
  min-height: 0;
  height: 100%;
  overflow: auto;
  background:
    radial-gradient(120% 80% at 0% 0%, rgba(255, 255, 255, 0.55), transparent 48%),
    var(--mac-app-surface, #fbfbfd);
  color: var(--mac-app-text, #1d1d1f);
}

.fm-view-list {
  display: flex;
  flex-direction: column;
}

.fm-list-header,
.fm-content-list .fm-entry {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 140px 92px 80px;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
}

.fm-list-header {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 30px;
  border-bottom: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
  background: color-mix(in srgb, var(--mac-app-surface-toolbar, rgba(246, 246, 250, 0.92)) 94%, white);
  backdrop-filter: var(--desktop-lg-filter-soft, blur(20px) saturate(150%));
  -webkit-backdrop-filter: var(--desktop-lg-filter-soft, blur(20px) saturate(150%));
}

.fm-list-header button {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 100%;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--mac-app-text-secondary, #6e6e73);
  font-size: 12px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
}

.fm-list-header button:hover { color: var(--mac-app-text, #1d1d1f); }
.fm-col-icon { pointer-events: none; }

.fm-content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
  align-content: start;
  gap: 6px 8px;
  padding: 16px 14px 18px;
}

.fm-content-list {
  display: grid;
  align-content: start;
  gap: 0;
  padding: 2px 0 8px;
}

.fm-content-list .fm-entry {
  min-height: 28px;
  padding-block: 3px;
  border-radius: 0;
}

.fm-entry {
  min-width: 0;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--mac-app-text, #242426);
  cursor: pointer;
  user-select: none;
  text-align: left;
  transition: background 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
}

.fm-content-grid .fm-entry {
  display: grid;
  place-items: center;
  align-content: start;
  gap: 8px;
  min-height: 112px;
  padding: 12px 8px 10px;
}

.fm-entry:hover {
  background: color-mix(in srgb, var(--mac-app-text, #242426) 5.5%, transparent);
}

.fm-entry-selected {
  border-color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 28%, transparent);
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 14%, transparent);
  box-shadow: inset 0 0 0 0.5px color-mix(in srgb, var(--mac-app-accent, #0a84ff) 22%, transparent);
  color: var(--mac-app-text, #1d1d1f);
}

.fm-content-list .fm-entry-selected {
  border-color: transparent;
  box-shadow: none;
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 16%, transparent);
}

.fm-entry-name {
  max-width: 100%;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.28;
  letter-spacing: -0.01em;
  text-overflow: ellipsis;
}

.fm-content-grid .fm-entry-name {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  text-align: center;
  width: 100%;
  word-break: break-word;
}

.fm-content-list .fm-entry-name {
  overflow: hidden;
  white-space: nowrap;
  text-align: left;
}

.fm-entry-date,
.fm-entry-kind,
.fm-entry-size {
  color: var(--mac-app-text-secondary, #77777c);
  font-size: 12px;
}

.fm-entry-kind,
.fm-entry-size { text-align: right; }

.fm-entry-selected .fm-entry-date,
.fm-entry-selected .fm-entry-kind,
.fm-entry-selected .fm-entry-size {
  color: color-mix(in srgb, var(--mac-app-text, #1d1d1f) 72%, #6e6e73);
}

.fm-state {
  display: grid;
  place-items: center;
  min-height: 100%;
  padding: 40px;
  color: var(--mac-app-text-secondary, #6e6e73);
  font-size: 13px;
}

.fm-empty {
  min-height: 100%;
}

.fm-state-error { align-content: center; }
.fm-load-banner { margin: 10px; }
</style>
