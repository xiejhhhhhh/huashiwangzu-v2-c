<template>
  <section class="fm-file-list" :class="`fm-view-${viewMode}`">
    <!-- Column headers (list view only) -->
    <div v-if="viewMode === 'list'" class="fm-list-header">
      <span class="fm-col-icon"></span>
      <button class="fm-col-name" type="button" @click="$emit('sort', 'name')">
        名称
        <span v-if="sortColumn === 'name'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <button class="fm-col-date" type="button" @click="$emit('sort', 'date')">
        修改日期
        <span v-if="sortColumn === 'date'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <button class="fm-col-type" type="button" @click="$emit('sort', 'type')">
        种类
        <span v-if="sortColumn === 'type'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <button class="fm-col-size" type="button" @click="$emit('sort', 'size')">
        大小
        <span v-if="sortColumn === 'size'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
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
      <div
        v-if="viewMode === 'grid'"
        class="fm-content-grid"
        :style="gridStyle"
      >
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
          <span class="fm-entry-icon-wrap" :style="iconWrapStyle">
            <FileVisualIcon
              :kind="item.is_folder || !item.format ? 'folder' : 'file'"
              :extension="item.format || ''"
              :size="gridIconSize"
            />
          </span>
          <span class="fm-entry-name" :style="nameStyle">{{ displayName(item) }}</span>
        </button>
      </div>

      <div v-else-if="viewMode === 'column'" class="fm-content-column">
        <div
          v-for="(col, colIndex) in effectiveColumns"
          :key="`col-${col.folderId}-${colIndex}`"
          class="fm-column-pane"
        >
          <button
            v-for="item in col.items"
            :key="`${item.is_folder ? 'folder' : 'file'}-${item.id}`"
            :draggable="false"
            class="fm-column-row"
            :data-selection-key="(item.is_folder ? 'folder' : 'file') + ':' + item.id"
            :data-folder="item.is_folder ? String(item.id) : undefined"
            :class="{ 'fm-entry-selected': col.selectedId === item.id }"
            type="button"
            @click="handleColumnClick(item, colIndex, $event)"
            @dblclick="handleColumnDoubleClick(item, colIndex, $event)"
            @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
            @mousedown.stop="handleEntryMouseDown(item, $event)"
          >
            <FileVisualIcon :kind="item.is_folder || !item.format ? 'folder' : 'file'" :extension="item.format || ''" :size="18" />
            <span class="fm-entry-name">{{ displayName(item) }}</span>
            <span v-if="item.is_folder" class="fm-column-chevron" aria-hidden="true">›</span>
          </button>
          <div v-if="!col.items.length" class="fm-column-empty">空文件夹</div>
        </div>
        <div class="fm-column-preview">
          <template v-if="columnPreviewItem">
            <FileVisualIcon
              :kind="columnPreviewItem.is_folder || !columnPreviewItem.format ? 'folder' : 'file'"
              :extension="columnPreviewItem.format || ''"
              :size="72"
            />
            <div class="fm-column-preview-name">{{ displayName(columnPreviewItem) }}</div>
            <div class="fm-column-preview-meta">
              {{ columnPreviewItem.is_folder ? '文件夹' : (columnPreviewItem.format || '文件') }}
              <template v-if="!columnPreviewItem.is_folder"> · {{ formatSize(columnPreviewItem.file_size) }}</template>
            </div>
          </template>
          <div v-else class="fm-column-preview-empty">选择一个项目以预览</div>
        </div>
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
          <FileVisualIcon :kind="item.is_folder || !item.format ? 'folder' : 'file'" :extension="item.format || ''" :size="18" />
          <span class="fm-entry-name">{{ displayName(item) }}</span>
          <span class="fm-entry-date">{{ formatListDate(item.created_at) }}</span>
          <span class="fm-entry-kind">{{ item.is_folder ? '文件夹' : ((item.format || '文件').toUpperCase()) }}</span>
          <span class="fm-entry-size">{{ item.is_folder ? '—' : formatSize(item.file_size) }}</span>
        </button>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import type { FileEntry } from '@/shared/api/types'
import { startDrag } from '@/desktop/drag-drop/drag-state'
import LoadStateBanner from '@/shared/components/load-state-banner.vue'
import { MacEmptyState } from '@/desktop/app-kit'
import type { ApiErrorInfo } from '@/shared/api/response-transform'
import type { LoadStatus } from '@/shared/composables/use-load-state'

let suppressNextClick = false
let pendingDrag: { key: string; startX: number; startY: number } | null = null

export type ColumnStackItem = {
  folderId: number
  name: string
  items: FileEntry[]
  selectedId: number | null
}

const props = withDefaults(defineProps<{
  items: FileEntry[]
  selectedId: number | null
  viewMode: 'grid' | 'list' | 'column'
  iconSize?: number
  columnStack?: ColumnStackItem[]
  loading: boolean
  displayName: (file: FileEntry) => string
  formatSize: (size: number) => string
  sortColumn: 'name' | 'date' | 'type' | 'size'
  sortDirection: 'asc' | 'desc'
  loadStatus: LoadStatus
  loadError: ApiErrorInfo | null
}>(), {
  iconSize: 50,
  columnStack: () => [],
})

const selected = computed(() => props.items.find((item) => item.id === props.selectedId) || null)

const effectiveColumns = computed<ColumnStackItem[]>(() => {
  if (props.columnStack?.length) return props.columnStack
  return [{
    folderId: 0,
    name: '当前',
    items: props.items,
    selectedId: props.selectedId,
  }]
})

const columnPreviewItem = computed(() => {
  const cols = effectiveColumns.value
  for (let i = cols.length - 1; i >= 0; i -= 1) {
    const col = cols[i]
    if (col.selectedId == null) continue
    const hit = col.items.find((item) => item.id === col.selectedId)
    if (hit) return hit
  }
  return selected.value
})

// mac Finder icon view proportions (reference FileIcon ~39×50 paper inside ~64×54.5 hit target)
const gridIconSize = computed(() => Math.max(28, Math.round(props.iconSize * 0.78)))
const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(auto-fill, minmax(${Math.max(80, props.iconSize + 30)}px, 1fr))`,
  gap: '10px',
}))
const iconWrapStyle = computed(() => ({
  width: `${Math.round(props.iconSize * 1.28)}px`,
  height: `${Math.round(props.iconSize * 1.09)}px`,
}))
const nameStyle = computed(() => ({
  maxWidth: `${Math.max(76, props.iconSize + 26)}px`,
}))

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
  (e: 'column-select', item: FileEntry, columnIndex: number): void
  (e: 'column-open', item: FileEntry, columnIndex: number): void
}>()

function handleColumnClick(item: FileEntry, columnIndex: number, e: MouseEvent) {
  if (suppressNextClick) {
    e.preventDefault()
    e.stopPropagation()
    suppressNextClick = false
    return
  }
  emit('column-select', item, columnIndex)
  emit('select', item)
}

function handleColumnDoubleClick(item: FileEntry, columnIndex: number, e: MouseEvent) {
  if (suppressNextClick) {
    e.preventDefault()
    e.stopPropagation()
    suppressNextClick = false
    return
  }
  if (item.is_folder) {
    emit('column-open', item, columnIndex)
    return
  }
  emit('open', item)
}

function formatListDate(raw?: string | null) {
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return String(raw).slice(0, 16)
  const now = new Date()
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (d.toDateString() === now.toDateString()) return `今天 ${time}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${time}`
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
</script>

<style scoped>
.fm-file-list {
  min-height: 0;
  height: 100%;
  overflow: auto;
  background: #fff;
  color: var(--mac-app-text, #1d1d1f);
}

.fm-view-list {
  display: flex;
  flex-direction: column;
}

.fm-list-header,
.fm-content-list .fm-entry {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 132px 88px 72px;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
}

.fm-list-header {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 24px;
  border-bottom: 0.5px solid rgba(60, 60, 67, 0.14);
  background: color-mix(in srgb, #f3f3f5 94%, white);
}

.fm-list-header button {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 100%;
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: rgba(60, 60, 67, 0.62);
  font: 500 11px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  text-align: left;
  cursor: pointer;
}

.fm-list-header button:hover { color: #1d1d1f; }
.fm-col-icon { pointer-events: none; }
.fm-sort-mark {
  font-size: 8px;
  opacity: 0.75;
}

.fm-content-grid {
  display: grid;
  align-content: start;
  padding: 12px;
  /* gap/columns set inline to track icon size slider */
}

.fm-content-column {
  display: flex;
  height: 100%;
  min-height: 0;
  overflow-x: auto;
  overflow-y: hidden;
  background: #fff;
}

.fm-column-pane {
  flex: 0 0 240px;
  width: 240px;
  overflow: auto;
  border-right: 0.5px solid rgba(60, 60, 67, 0.14);
  background: #fff;
  padding: 4px 0;
}

.fm-column-empty {
  padding: 16px 12px;
  color: rgba(60, 60, 67, 0.45);
  font-size: 12px;
}

.fm-column-row {
  width: 100%;
  min-height: 28px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 12px;
  align-items: center;
  gap: 8px;
  text-align: left;
  cursor: default;
  color: #1d1d1f;
  font-size: 13px;
}

.fm-column-row:hover {
  background: rgba(0, 0, 0, 0.05);
}

.fm-column-row.fm-entry-selected {
  background: rgba(10, 132, 255, 0.18);
}

.fm-column-chevron {
  color: rgba(60, 60, 67, 0.45);
  font-size: 14px;
}

.fm-column-preview {
  flex: 1 1 220px;
  min-width: 200px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  padding: 24px;
  background: #fbfbfd;
  color: #1d1d1f;
}

.fm-column-preview-name {
  max-width: 240px;
  text-align: center;
  font: 600 13px/1.3 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  word-break: break-word;
}

.fm-column-preview-meta,
.fm-column-preview-empty {
  color: rgba(60, 60, 67, 0.58);
  font-size: 12px;
}

.fm-content-list {
  display: grid;
  align-content: start;
  gap: 0;
  padding: 2px 0 8px;
}

.fm-content-list .fm-entry {
  min-height: 26px;
  padding-block: 2px;
  border-radius: 0;
}

.fm-entry {
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--mac-app-text, #1d1d1f);
  cursor: default;
  user-select: none;
  text-align: left;
}

.fm-content-grid .fm-entry {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  padding: 4px 2px;
  border-radius: 0;
  opacity: 1;
}

.fm-entry-icon-wrap {
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: transparent;
  transition: background 100ms ease;
}

.fm-content-grid .fm-entry:hover .fm-entry-icon-wrap {
  background: rgba(0, 0, 0, 0.045);
}

.fm-content-grid .fm-entry-selected .fm-entry-icon-wrap {
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 15%, transparent);
}

.fm-content-list .fm-entry:hover {
  background: rgba(0, 0, 0, 0.04);
}

.fm-content-list .fm-entry-selected {
  background: rgba(10, 132, 255, 0.18);
}

.fm-content-list .fm-entry-selected .fm-entry-date,
.fm-content-list .fm-entry-selected .fm-entry-kind,
.fm-content-list .fm-entry-selected .fm-entry-size {
  color: rgba(29, 29, 31, 0.72);
}

.fm-entry-name {
  max-width: 100%;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
}

.fm-content-grid .fm-entry-name {
  margin-top: 3px;
  padding: 1px 5px;
  border-radius: 5px;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  text-align: center;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.25;
  color: var(--mac-app-text, #1d1d1f);
  background: transparent;
}

.fm-content-grid .fm-entry-selected .fm-entry-name {
  background: var(--mac-app-accent, #0a84ff);
  color: #fff;
}

.fm-content-list .fm-entry-name {
  overflow: hidden;
  white-space: nowrap;
  text-align: left;
}

.fm-entry-date,
.fm-entry-kind,
.fm-entry-size {
  color: rgba(60, 60, 67, 0.58);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fm-entry-kind,
.fm-entry-size { text-align: right; }

.fm-content-list .fm-entry-name {
  font-size: 13px;
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
