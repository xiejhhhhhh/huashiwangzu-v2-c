<template>
  <section class="fm-file-list" :class="`fm-view-${viewMode}`">
    <!-- Column headers (list view only) -->
    <div v-if="viewMode === 'list'" class="fm-list-header" :style="listGridStyle">
      <span class="fm-col-icon"></span>
      <button class="fm-col-name" type="button" @click="$emit('sort', 'name')">
        名称
        <span v-if="sortColumn === 'name'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <span class="fm-col-resizer" @mousedown.prevent.stop="startColumnResize('name', $event)" />
      <button class="fm-col-date" type="button" @click="$emit('sort', 'date')">
        修改日期
        <span v-if="sortColumn === 'date'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <span class="fm-col-resizer" @mousedown.prevent.stop="startColumnResize('date', $event)" />
      <button class="fm-col-type" type="button" @click="$emit('sort', 'type')">
        种类
        <span v-if="sortColumn === 'type'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <span class="fm-col-resizer" @mousedown.prevent.stop="startColumnResize('type', $event)" />
      <button class="fm-col-size" type="button" @click="$emit('sort', 'size')">
        大小
        <span v-if="sortColumn === 'size'" class="fm-sort-mark">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
      </button>
      <span class="fm-col-resizer" @mousedown.prevent.stop="startColumnResize('size', $event)" />
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
          :class="{ 'fm-entry-selected': isSelected(item.id), 'fm-entry-drop': isDropTarget(item) }"
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
          <span v-if="itemTags(item).length" class="fm-entry-tags">
            <i v-for="tag in itemTags(item)" :key="tag" class="fm-entry-tag-dot" :style="{ background: tagColor(tag) }" />
          </span>
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
            :class="{ 'fm-entry-selected': col.selectedId === item.id, 'fm-entry-drop': isDropTarget(item) }"
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
            <div v-if="columnMedia.loading" class="fm-column-preview-empty">加载预览…</div>
            <img
              v-else-if="columnMedia.mode === 'image' && columnMedia.objectUrl"
              class="fm-column-preview-media"
              :src="columnMedia.objectUrl"
              :alt="displayName(columnPreviewItem)"
            >
            <iframe
              v-else-if="columnMedia.mode === 'pdf' && columnMedia.objectUrl"
              class="fm-column-preview-pdf"
              :src="columnMedia.objectUrl"
              title="PDF 预览"
            />
            <pre v-else-if="columnMedia.mode === 'text'" class="fm-column-preview-text">{{ columnMedia.text }}</pre>
            <FileVisualIcon
              v-else
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

      <div
        v-else-if="viewMode === 'gallery'"
        class="fm-content-gallery"
      >
        <div class="fm-gallery-stage">
          <template v-if="selected">
            <div v-if="galleryPreview.loading" class="fm-gallery-state">加载预览…</div>
            <img
              v-else-if="galleryPreview.mode === 'image' && galleryPreview.objectUrl"
              class="fm-gallery-media"
              :src="galleryPreview.objectUrl"
              :alt="displayName(selected)"
            >
            <iframe
              v-else-if="galleryPreview.mode === 'pdf' && galleryPreview.objectUrl"
              class="fm-gallery-pdf"
              :src="galleryPreview.objectUrl"
              title="PDF 预览"
            />
            <pre v-else-if="galleryPreview.mode === 'text'" class="fm-gallery-text">{{ galleryPreview.text }}</pre>
            <template v-else>
              <FileVisualIcon
                :kind="selected.is_folder || !selected.format ? 'folder' : 'file'"
                :extension="selected.format || ''"
                :size="148"
              />
            </template>
            <div class="fm-gallery-name">{{ displayName(selected) }}</div>
            <div class="fm-gallery-meta">
              {{ selected.is_folder ? '文件夹' : ((selected.format || '文件').toUpperCase()) }}
              <template v-if="!selected.is_folder"> · {{ formatSize(selected.file_size) }}</template>
              <template v-if="galleryPreview.truncated"> · 已截断</template>
            </div>
          </template>
          <div v-else class="fm-gallery-empty">选择一个项目以在画廊中预览</div>
        </div>
        <div class="fm-gallery-strip">
          <button
            v-for="item in items"
            :key="`g-${item.is_folder ? 'folder' : 'file'}-${item.id}`"
            type="button"
            class="fm-gallery-thumb"
            :class="{ 'fm-entry-selected': isSelected(item.id), 'fm-entry-drop': isDropTarget(item) }"
            :data-selection-key="(item.is_folder ? 'folder' : 'file') + ':' + item.id"
            @click="handleClick(item, $event)"
            @dblclick="handleDoubleClick(item, $event)"
            @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
            @mousedown.stop="handleEntryMouseDown(item, $event)"
          >
            <img
              v-if="stripThumbs[item.id]"
              class="fm-gallery-strip-img"
              :src="stripThumbs[item.id]"
              :alt="displayName(item)"
            >
            <FileVisualIcon
              v-else
              :kind="item.is_folder || !item.format ? 'folder' : 'file'"
              :extension="item.format || ''"
              :size="42"
            />
            <span class="fm-gallery-thumb-name">{{ displayName(item) }}</span>
          </button>
        </div>
      </div>

      <div v-else class="fm-content-list">
        <button
          v-for="item in items"
          :key="`${item.is_folder ? 'folder' : 'file'}-${item.id}`"
          :draggable="false"
          class="fm-entry"
          :style="listGridStyle"
          :data-selection-key="(item.is_folder ? 'folder' : 'file') + ':' + item.id"
          :data-folder="item.is_folder ? String(item.id) : undefined"
          :class="{ 'fm-entry-selected': isSelected(item.id), 'fm-entry-drop': isDropTarget(item) }"
          type="button"
          @click="handleClick(item, $event)"
          @dblclick="handleDoubleClick(item, $event)"
          @contextmenu.prevent.stop="$emit('context-menu', item, $event)"
          @mousedown.stop="handleEntryMouseDown(item, $event)"
        >
          <FileVisualIcon :kind="item.is_folder || !item.format ? 'folder' : 'file'" :extension="item.format || ''" :size="18" />
          <span class="fm-entry-name" @click.stop="maybeStartInlineRename(item, $event)">
            <input
              v-if="renamingId === item.id"
              class="fm-inline-rename"
              :value="renameDraft"
              @mousedown.stop
              @click.stop
              @keydown.enter.prevent="commitInlineRename(item)"
              @keydown.esc.prevent="cancelInlineRename"
              @blur="commitInlineRename(item)"
            >
            <template v-else>
              {{ displayName(item) }}
              <span v-if="itemTags(item).length" class="fm-entry-tags inline">
                <i v-for="tag in itemTags(item)" :key="tag" class="fm-entry-tag-dot" :style="{ background: tagColor(tag) }" />
              </span>
            </template>
          </span>
          <span class="fm-entry-spacer" aria-hidden="true" />
          <span class="fm-entry-date">{{ formatListDate(item.updated_at || item.created_at) }}</span>
          <span class="fm-entry-spacer" aria-hidden="true" />
          <span class="fm-entry-kind">{{ item.is_folder ? '文件夹' : kindLabel(item) }}</span>
          <span class="fm-entry-spacer" aria-hidden="true" />
          <span class="fm-entry-size">{{ item.is_folder ? '—' : formatSize(item.file_size) }}</span>
          <span class="fm-entry-spacer" aria-hidden="true" />
        </button>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import type { FileEntry } from '@/shared/api/types'
import { startDrag, dragState } from '@/desktop/drag-drop/drag-state'
import { fetchBlobByApiPath, fetchDownloadBlob, fetchFilePreview } from '@/shared/api/desktop'
import LoadStateBanner from '@/shared/components/load-state-banner.vue'
import { MacEmptyState } from '@/desktop/app-kit'
import { FINDER_TAGS } from './finder-tags'
import type { ApiErrorInfo } from '@/shared/api/response-transform'
import type { LoadStatus } from '@/shared/composables/use-load-state'

let suppressNextClick = false
let pendingDrag: { key: string; keys: string[]; startX: number; startY: number } | null = null

export type ColumnStackItem = {
  folderId: number
  name: string
  items: FileEntry[]
  selectedId: number | null
}

export type ListColumnWidths = {
  name?: number
  date?: number
  type?: number
  size?: number
}

type ResizableColumn = 'name' | 'date' | 'type' | 'size'

const DEFAULT_COLUMN_WIDTHS: Required<ListColumnWidths> = {
  name: 220,
  date: 132,
  type: 88,
  size: 72,
}

const COLUMN_LIMITS: Record<ResizableColumn, { min: number; max: number }> = {
  name: { min: 120, max: 560 },
  date: { min: 96, max: 240 },
  type: { min: 64, max: 180 },
  size: { min: 56, max: 140 },
}

const props = withDefaults(defineProps<{
  items: FileEntry[]
  selectedId: number | null
  selectedIds?: number[]
  viewMode: 'grid' | 'list' | 'column' | 'gallery'
  iconSize?: number
  columnStack?: ColumnStackItem[]
  columnWidths?: ListColumnWidths
  loading: boolean
  displayName: (file: FileEntry) => string
  formatSize: (size: number) => string
  tagsOf?: (file: FileEntry) => string[]
  tagRevision?: number
  sortColumn: 'name' | 'date' | 'type' | 'size'
  sortDirection: 'asc' | 'desc'
  loadStatus: LoadStatus
  loadError: ApiErrorInfo | null
}>(), {
  iconSize: 50,
  columnStack: () => [],
  // defineProps defaults are hoisted — cannot close over setup locals
  columnWidths: () => ({ name: 220, date: 132, type: 88, size: 72 }),
  selectedIds: () => [],
  tagsOf: () => [],
  tagRevision: 0,
})

function isSelected(id: number) {
  if (props.selectedIds?.length) return props.selectedIds.includes(id)
  return props.selectedId === id
}

function isDropTarget(item: FileEntry) {
  if (!item.is_folder || !dragState.isDragging || !dragState.dragOverId) return false
  if (dragState.dragOverId !== String(item.id)) return false
  // cannot drop onto self / currently dragged folder
  if (dragState.draggedIds.some((key) => key === `folder:${item.id}` || key.endsWith(`:${item.id}`))) {
    return false
  }
  return true
}

function itemTags(item: FileEntry) {
  void props.tagRevision
  return props.tagsOf ? props.tagsOf(item) : []
}
function tagColor(tag: string) {
  return FINDER_TAGS.find((t) => t.key === tag)?.color || 'rgb(152,152,157)'
}

const selected = computed(() => props.items.find((item) => item.id === props.selectedId) || null)

const IMAGE_EXTS = new Set([
  'jpg', 'jpeg', 'jpe', 'jfif', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tif', 'tiff', 'avif',
])
const TEXT_EXTS = new Set([
  'txt', 'md', 'json', 'csv', 'log', 'xml', 'yaml', 'yml', 'ini', 'cfg', 'conf', 'env', 'sql', 'toml',
  'php', 'js', 'ts', 'jsx', 'tsx', 'css', 'scss', 'less', 'html', 'htm', 'vue',
  'py', 'java', 'go', 'rs', 'c', 'cpp', 'h', 'hpp', 'cs', 'rb', 'sh', 'bash', 'zsh',
])

type GalleryPreviewMode = 'idle' | 'image' | 'pdf' | 'text' | 'fallback'
const galleryPreview = reactive({
  loading: false,
  mode: 'idle' as GalleryPreviewMode,
  text: '',
  objectUrl: '',
  truncated: false,
})
const columnMedia = reactive({
  loading: false,
  mode: 'idle' as GalleryPreviewMode,
  text: '',
  objectUrl: '',
})
const stripThumbs = reactive<Record<number, string>>({})
let galleryToken = 0
let columnToken = 0
let stripToken = 0

function extOf(item: FileEntry) {
  return String(item.format || '').toLowerCase().replace(/^\./, '')
}
function asString(value: unknown) {
  return typeof value === 'string' ? value : ''
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function revokeGalleryUrl() {
  if (galleryPreview.objectUrl) {
    URL.revokeObjectURL(galleryPreview.objectUrl)
    galleryPreview.objectUrl = ''
  }
}

function resetGalleryPreview() {
  revokeGalleryUrl()
  galleryPreview.loading = false
  galleryPreview.mode = 'idle'
  galleryPreview.text = ''
  galleryPreview.truncated = false
}

async function resolveMediaBlob(data: Record<string, unknown>, fileId: number, preferStandardImage: boolean) {
  const downloadUrl = asString(data.download_url)
  if (downloadUrl) {
    try {
      return await fetchBlobByApiPath(downloadUrl)
    } catch {
      // fall through
    }
  }
  if (preferStandardImage) {
    try {
      return await fetchDownloadBlob(fileId, 'standard-image')
    } catch {
      // fall through
    }
  }
  return await fetchDownloadBlob(fileId)
}

async function loadGalleryPreview(item: FileEntry | null) {
  const token = ++galleryToken
  resetGalleryPreview()
  if (!item || item.is_folder) {
    galleryPreview.mode = 'fallback'
    return
  }
  galleryPreview.loading = true
  const ext = extOf(item)
  try {
    const data = await fetchFilePreview(item.id)
    if (token !== galleryToken) return
    if (!isRecord(data)) throw new Error('invalid preview')
    const content = asString(data.content)
    if (content) {
      galleryPreview.mode = 'text'
      galleryPreview.text = content
      galleryPreview.truncated = content.includes('--- File too long')
      return
    }
    const mime = asString(data.mime_type).toLowerCase()
    const looksImage = mime.startsWith('image/') || IMAGE_EXTS.has(ext)
    const looksPdf = mime === 'application/pdf' || ext === 'pdf'
    if (looksImage) {
      const blob = await resolveMediaBlob(data, item.id, true)
      if (token !== galleryToken) return
      galleryPreview.objectUrl = URL.createObjectURL(blob)
      galleryPreview.mode = 'image'
      return
    }
    if (looksPdf) {
      const blob = await resolveMediaBlob(data, item.id, false)
      if (token !== galleryToken) return
      galleryPreview.objectUrl = URL.createObjectURL(blob)
      galleryPreview.mode = 'pdf'
      return
    }
    if (TEXT_EXTS.has(ext)) {
      galleryPreview.mode = 'text'
      galleryPreview.text = content || '(空文件)'
      return
    }
    galleryPreview.mode = 'fallback'
  } catch {
    if (token !== galleryToken) return
    try {
      if (IMAGE_EXTS.has(ext)) {
        const blob = await fetchDownloadBlob(item.id)
        if (token !== galleryToken) return
        galleryPreview.objectUrl = URL.createObjectURL(blob)
        galleryPreview.mode = 'image'
        return
      }
      if (ext === 'pdf') {
        const blob = await fetchDownloadBlob(item.id)
        if (token !== galleryToken) return
        galleryPreview.objectUrl = URL.createObjectURL(blob)
        galleryPreview.mode = 'pdf'
        return
      }
    } catch {
      // keep fallback
    }
    galleryPreview.mode = 'fallback'
  } finally {
    if (token === galleryToken) galleryPreview.loading = false
  }
}

function clearStripThumbs() {
  Object.keys(stripThumbs).forEach((key) => {
    const id = Number(key)
    if (stripThumbs[id]) URL.revokeObjectURL(stripThumbs[id])
    delete stripThumbs[id]
  })
}

async function loadStripThumbs(items: FileEntry[]) {
  const token = ++stripToken
  clearStripThumbs()
  const images = items.filter((item) => !item.is_folder && IMAGE_EXTS.has(extOf(item))).slice(0, 24)
  for (const item of images) {
    if (token !== stripToken) return
    try {
      const data = await fetchFilePreview(item.id)
      if (token !== stripToken) return
      let blob: Blob
      if (isRecord(data)) {
        blob = await resolveMediaBlob(data, item.id, true)
      } else {
        blob = await fetchDownloadBlob(item.id, 'standard-image').catch(() => fetchDownloadBlob(item.id))
      }
      if (token !== stripToken) return
      stripThumbs[item.id] = URL.createObjectURL(blob)
    } catch {
      // keep icon
    }
  }
}

function revokeColumnUrl() {
  if (columnMedia.objectUrl) {
    URL.revokeObjectURL(columnMedia.objectUrl)
    columnMedia.objectUrl = ''
  }
}
function resetColumnMedia() {
  revokeColumnUrl()
  columnMedia.loading = false
  columnMedia.mode = 'idle'
  columnMedia.text = ''
}

async function loadColumnMedia(item: FileEntry | null) {
  const token = ++columnToken
  resetColumnMedia()
  if (!item || item.is_folder) {
    columnMedia.mode = 'fallback'
    return
  }
  columnMedia.loading = true
  const ext = extOf(item)
  try {
    const data = await fetchFilePreview(item.id)
    if (token !== columnToken) return
    if (!isRecord(data)) throw new Error('invalid preview')
    const content = asString(data.content)
    if (content) {
      columnMedia.mode = 'text'
      columnMedia.text = content
      return
    }
    const mime = asString(data.mime_type).toLowerCase()
    if (mime.startsWith('image/') || IMAGE_EXTS.has(ext)) {
      const blob = await resolveMediaBlob(data, item.id, true)
      if (token !== columnToken) return
      columnMedia.objectUrl = URL.createObjectURL(blob)
      columnMedia.mode = 'image'
      return
    }
    if (mime === 'application/pdf' || ext === 'pdf') {
      const blob = await resolveMediaBlob(data, item.id, false)
      if (token !== columnToken) return
      columnMedia.objectUrl = URL.createObjectURL(blob)
      columnMedia.mode = 'pdf'
      return
    }
    if (TEXT_EXTS.has(ext)) {
      columnMedia.mode = 'text'
      columnMedia.text = content || '(空文件)'
      return
    }
    columnMedia.mode = 'fallback'
  } catch {
    if (token !== columnToken) return
    try {
      if (IMAGE_EXTS.has(ext)) {
        const blob = await fetchDownloadBlob(item.id)
        if (token !== columnToken) return
        columnMedia.objectUrl = URL.createObjectURL(blob)
        columnMedia.mode = 'image'
        return
      }
      if (ext === 'pdf') {
        const blob = await fetchDownloadBlob(item.id)
        if (token !== columnToken) return
        columnMedia.objectUrl = URL.createObjectURL(blob)
        columnMedia.mode = 'pdf'
        return
      }
    } catch {
      // fallback icon
    }
    columnMedia.mode = 'fallback'
  } finally {
    if (token === columnToken) columnMedia.loading = false
  }
}

watch(
  () => [props.viewMode, selected.value?.id, selected.value?.format, selected.value?.is_folder] as const,
  () => {
    if (props.viewMode !== 'gallery') {
      galleryToken += 1
      resetGalleryPreview()
      return
    }
    void loadGalleryPreview(selected.value)
  },
  { immediate: true },
)

watch(
  () => [props.viewMode, props.items.map((item) => `${item.id}:${item.format || ''}`).join('|')] as const,
  () => {
    if (props.viewMode !== 'gallery') {
      stripToken += 1
      clearStripThumbs()
      return
    }
    void loadStripThumbs(props.items)
  },
  { immediate: true },
)

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

watch(
  () => [props.viewMode, columnPreviewItem.value?.id, columnPreviewItem.value?.format, columnPreviewItem.value?.is_folder] as const,
  () => {
    if (props.viewMode !== 'column') {
      columnToken += 1
      resetColumnMedia()
      return
    }
    void loadColumnMedia(columnPreviewItem.value)
  },
  { immediate: true },
)

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

function selectionKeyOf(item: FileEntry) {
  return (item.is_folder ? 'folder' : 'file') + ':' + item.id
}

function resolveDragKeys(item: FileEntry): string[] {
  const primary = selectionKeyOf(item)
  if (props.selectedIds?.includes(item.id) && props.selectedIds.length > 1) {
    const byId = new Map(props.items.map((entry) => [entry.id, entry]))
    const keys = props.selectedIds
      .map((id) => byId.get(id))
      .filter((entry): entry is FileEntry => Boolean(entry))
      .map(selectionKeyOf)
    if (keys.length) {
      // keep primary first for ghost origin
      return [primary, ...keys.filter((key) => key !== primary)]
    }
  }
  return [primary]
}

function handleEntryMouseDown(item: FileEntry, e: MouseEvent) {
  if (e.button !== 0) return
  pendingDrag = {
    key: selectionKeyOf(item),
    keys: resolveDragKeys(item),
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
  startDrag(pendingDrag.keys, pendingDrag.startX, pendingDrag.startY, { copyMode: e.altKey })
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
  emit('select', item, { additive: e.metaKey || e.ctrlKey, range: e.shiftKey })
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
  (e: 'select', item: FileEntry, opts?: { additive?: boolean; range?: boolean }): void
  (e: 'open', item: FileEntry): void
  (e: 'context-menu', item: FileEntry, event: MouseEvent): void
  (e: 'sort', column: string): void
  (e: 'update:columnWidths', value: Required<ListColumnWidths>): void
  (e: 'rename-inline', item: FileEntry, nextName: string): void
  (e: 'retry'): void
  (e: 'column-select', item: FileEntry, columnIndex: number): void
  (e: 'column-open', item: FileEntry, columnIndex: number): void
}>()

const renamingId = ref<number | null>(null)
const renameDraft = ref('')
let renameClickTimer: ReturnType<typeof setTimeout> | null = null
let lastRenameClickId: number | null = null

function kindLabel(item: FileEntry) {
  if (item.is_folder) return '文件夹'
  const ext = String(item.format || '').toLowerCase()
  if (!ext) return '文件'
  const map: Record<string, string> = {
    pdf: 'PDF 文稿',
    png: 'PNG 图像',
    jpg: 'JPEG 图像',
    jpeg: 'JPEG 图像',
    gif: 'GIF 图像',
    webp: 'WebP 图像',
    svg: 'SVG 图像',
    txt: '纯文本',
    md: 'Markdown',
    json: 'JSON',
    csv: 'CSV',
    zip: 'ZIP 归档',
    mp4: 'MPEG-4 影片',
    mov: 'QuickTime 影片',
    mp3: 'MP3 音频',
    wav: 'WAV 音频',
    doc: 'Word 文稿',
    docx: 'Word 文稿',
    xls: 'Excel 表格',
    xlsx: 'Excel 表格',
    ppt: 'PowerPoint',
    pptx: 'PowerPoint',
    js: 'JavaScript',
    ts: 'TypeScript',
    vue: 'Vue 源码',
    py: 'Python 源码',
    php: 'PHP 源码',
  }
  return map[ext] || `${ext.toUpperCase()} 文件`
}

function maybeStartInlineRename(item: FileEntry, e: MouseEvent) {
  if (!isSelected(item.id)) return
  // second click on already-selected name starts rename (Finder-like slow double click)
  if (lastRenameClickId === item.id) {
    if (renameClickTimer) clearTimeout(renameClickTimer)
    renameClickTimer = null
    lastRenameClickId = null
    startInlineRename(item)
    e.preventDefault()
    return
  }
  lastRenameClickId = item.id
  if (renameClickTimer) clearTimeout(renameClickTimer)
  renameClickTimer = setTimeout(() => {
    lastRenameClickId = null
    renameClickTimer = null
  }, 900)
}

function startInlineRename(item: FileEntry) {
  renamingId.value = item.id
  renameDraft.value = item.file_name
  requestAnimationFrame(() => {
    const el = document.querySelector('.fm-inline-rename') as HTMLInputElement | null
    el?.focus()
    el?.select()
  })
}

function cancelInlineRename() {
  renamingId.value = null
  renameDraft.value = ''
}

function commitInlineRename(item: FileEntry) {
  if (renamingId.value !== item.id) return
  const next = renameDraft.value.trim()
  renamingId.value = null
  renameDraft.value = ''
  if (!next || next === item.file_name) return
  emit('rename-inline', item, next)
}

const resolvedColumnWidths = computed(() => ({
  name: props.columnWidths?.name ?? DEFAULT_COLUMN_WIDTHS.name,
  date: props.columnWidths?.date ?? DEFAULT_COLUMN_WIDTHS.date,
  type: props.columnWidths?.type ?? DEFAULT_COLUMN_WIDTHS.type,
  size: props.columnWidths?.size ?? DEFAULT_COLUMN_WIDTHS.size,
}))

const listGridStyle = computed(() => {
  const w = resolvedColumnWidths.value
  // name is flexible floor; other columns fixed px (Finder-like)
  // trailing 6px track hosts the size-column resizer in the header
  return {
    gridTemplateColumns: `24px minmax(${w.name}px, 1fr) 6px ${w.date}px 6px ${w.type}px 6px ${w.size}px 6px`,
  }
})

const resizing = ref<null | { column: ResizableColumn; startX: number; startWidth: number }>(null)

function clampColumnWidth(column: ResizableColumn, value: number) {
  const limit = COLUMN_LIMITS[column]
  return Math.min(limit.max, Math.max(limit.min, Math.round(value)))
}

function startColumnResize(column: ResizableColumn, e: MouseEvent) {
  resizing.value = {
    column,
    startX: e.clientX,
    startWidth: resolvedColumnWidths.value[column],
  }
  document.addEventListener('mousemove', onColumnResizeMove)
  document.addEventListener('mouseup', onColumnResizeEnd)
}

function onColumnResizeMove(e: MouseEvent) {
  if (!resizing.value) return
  const delta = e.clientX - resizing.value.startX
  const nextWidth = clampColumnWidth(resizing.value.column, resizing.value.startWidth + delta)
  emit('update:columnWidths', {
    ...resolvedColumnWidths.value,
    [resizing.value.column]: nextWidth,
  })
}

function onColumnResizeEnd() {
  document.removeEventListener('mousemove', onColumnResizeMove)
  document.removeEventListener('mouseup', onColumnResizeEnd)
  resizing.value = null
}

onBeforeUnmount(() => {
  onColumnResizeEnd()
  clearPendingDrag()
  galleryToken += 1
  columnToken += 1
  stripToken += 1
  resetGalleryPreview()
  resetColumnMedia()
  clearStripThumbs()
})

function handleColumnClick(item: FileEntry, columnIndex: number, e: MouseEvent) {
  if (suppressNextClick) {
    e.preventDefault()
    e.stopPropagation()
    suppressNextClick = false
    return
  }
  emit('column-select', item, columnIndex)
  emit('select', item, { additive: e.metaKey || e.ctrlKey, range: e.shiftKey })
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
  /* widths injected via listGridStyle */
  grid-template-columns: 24px minmax(220px, 1fr) 6px 132px 6px 88px 6px 72px 6px;
  align-items: center;
  gap: 0 2px;
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
  min-width: 0;
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
.fm-col-resizer {
  width: 6px;
  height: 100%;
  cursor: col-resize;
  position: relative;
}
.fm-col-resizer::after {
  content: '';
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 2px;
  width: 1px;
  background: rgba(60, 60, 67, 0.18);
}
.fm-col-resizer:hover::after {
  background: rgba(10, 132, 255, 0.55);
}
.fm-entry-spacer {
  width: 6px;
  pointer-events: none;
}
.fm-sort-mark {
  font-size: 8px;
  opacity: 0.75;
}
.fm-entry-name,
.fm-entry-date,
.fm-entry-kind,
.fm-entry-size {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fm-inline-rename {
  width: 100%;
  min-width: 80px;
  height: 20px;
  margin: 0;
  padding: 0 4px;
  border: 1px solid var(--mac-app-accent, #0a84ff);
  border-radius: 4px;
  outline: none;
  background: #fff;
  color: #1d1d1f;
  font: 400 12px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--mac-app-accent, #0a84ff) 25%, transparent);
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
  flex: 0 0 var(--fm-miller-col-width, 240px);
  width: var(--fm-miller-col-width, 240px);
  min-width: 160px;
  max-width: 420px;
  overflow: auto;
  resize: horizontal;
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
.fm-column-preview-media {
  max-width: min(280px, 90%);
  max-height: 220px;
  object-fit: contain;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
}
.fm-column-preview-pdf {
  width: min(300px, 92%);
  height: 220px;
  border: 0;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
}
.fm-column-preview-text {
  width: min(300px, 92%);
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
  font: 11px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  text-align: left;
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

.fm-content-gallery {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) 118px;
  background: #fff;
}
.fm-gallery-stage {
  min-height: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 12px;
  padding: 24px;
  background:
    radial-gradient(120% 90% at 50% 0%, rgba(255,255,255,0.9), transparent 55%),
    #f7f7f9;
}
.fm-gallery-media {
  max-width: min(720px, 90%);
  max-height: min(420px, 62vh);
  object-fit: contain;
  border-radius: 10px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.12);
  background: #fff;
}
.fm-gallery-pdf {
  width: min(760px, 92%);
  height: min(420px, 62vh);
  border: 0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.12);
}
.fm-gallery-text {
  width: min(720px, 92%);
  max-height: min(420px, 62vh);
  overflow: auto;
  margin: 0;
  padding: 14px 16px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08);
  color: #1d1d1f;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  text-align: left;
}
.fm-gallery-state {
  color: rgba(60, 60, 67, 0.55);
  font-size: 13px;
}
.fm-gallery-name {
  max-width: 420px;
  text-align: center;
  font: 600 14px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: #1d1d1f;
  word-break: break-word;
}
.fm-gallery-meta,
.fm-gallery-empty {
  color: rgba(60, 60, 67, 0.55);
  font-size: 12px;
}
.fm-gallery-strip {
  display: flex;
  gap: 8px;
  align-items: stretch;
  overflow-x: auto;
  padding: 10px 12px;
  border-top: 0.5px solid rgba(60, 60, 67, 0.14);
  background: color-mix(in srgb, #f4f4f6 90%, white);
}
.fm-gallery-thumb {
  flex: 0 0 88px;
  width: 88px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  padding: 8px 6px;
  display: grid;
  justify-items: center;
  gap: 6px;
  cursor: default;
  color: #1d1d1f;
}
.fm-gallery-strip-img {
  width: 42px;
  height: 42px;
  object-fit: cover;
  border-radius: 6px;
  background: #fff;
  box-shadow: inset 0 0 0 0.5px rgba(60, 60, 67, 0.16);
}
.fm-gallery-thumb:hover {
  background: rgba(0,0,0,0.05);
}
.fm-gallery-thumb.fm-entry-selected {
  background: rgba(10, 132, 255, 0.16);
}
.fm-gallery-thumb-name {
  width: 100%;
  font-size: 11px;
  line-height: 1.2;
  text-align: center;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}

.fm-entry-tags {
  display: inline-flex;
  gap: 3px;
  align-items: center;
  justify-content: center;
  min-height: 8px;
}
.fm-entry-tags.inline {
  margin-left: 6px;
  vertical-align: middle;
}
.fm-entry-tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
  box-shadow: inset 0 0 0 0.5px rgba(0,0,0,0.2);
}

.fm-entry.fm-entry-drop,
.fm-column-row.fm-entry-drop,
.fm-gallery-thumb.fm-entry-drop {
  box-shadow: inset 0 0 0 2px rgba(0, 122, 255, 0.55);
  background: color-mix(in srgb, rgba(0, 122, 255, 0.12) 70%, rgba(255, 255, 255, 0.5));
}
</style>
