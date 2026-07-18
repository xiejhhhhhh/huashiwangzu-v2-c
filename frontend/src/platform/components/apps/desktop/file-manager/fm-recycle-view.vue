<template>
  <div class="fm-recycle-view" @contextmenu.prevent="handleBlankMenu">
    <div class="rv-toolbar">
      <span class="rv-title">回收站</span>
      <el-button size="small" :icon="Refresh" @click="loadList">刷新</el-button>
      <el-button size="small" :disabled="!canWrite || items.length === 0" @click="emptyTrash">清空回收站</el-button>
    </div>

    <FmFileList
      :items="sortedFileEntries"
      :selected-id="selectedId"
      :view-mode="viewMode"
      :loading="loading"
      :display-name="displayName"
      :format-size="formatSize"
      :sort-column="sortColumn"
      :sort-direction="sortDirection"
      :load-status="loadState.status"
      :load-error="loadState.error"
      @select="handleSelect"
      @open="handleOpen"
      @context-menu="handleItemContextMenu"
      @sort="handleSort"
      @retry="loadList"
    />

    <FmStatusBar
      :item-count="items.length"
      :folder-count="folders.length"
      :file-count="files.length"
      :selected-item="selectedFileEntry"
      :selected-size="selectedFileEntry ? formatSize(selectedFileEntry.file_size) : ''"
      :view-mode="viewMode"
      :search-keyword="searchKeyword"
      :filtered-count="sortedFileEntries.length"
      :display-name="displayName"
      @update:view-mode="viewMode = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useAppFeedback } from '@/desktop/app-kit'
import { fetchRecycleBinList, emptyRecycleBinRequest } from '@/shared/api/desktop'
import type { RecycleBinEntry } from '@/shared/api/types'
import type { FileEntry } from '@/shared/api/types'
import { usePermission } from '@/shared/composables/use-permission'
import { formatFileDisplayName } from '@/shared/files/display-name'
import { createLoadState, failLoading, finishLoading, startLoading } from '@/shared/composables/use-load-state'
import FmFileList from './fm-file-list.vue'
import FmStatusBar from './fm-status-bar.vue'
import emitter from '@/desktop/events'

const feedback = useAppFeedback()

const emit = defineEmits<{
  (e: 'context-menu-blank', event: MouseEvent, options: { key: string; label: string; icon?: string; danger?: boolean }[]): void
  (e: 'context-menu-item', event: MouseEvent, item: RecycleBinEntry, options: { key: string; label: string; icon?: string; danger?: boolean }[]): void
}>()

const { isEditorOrAbove } = usePermission()
const canWrite = ref(false)
const items = ref<RecycleBinEntry[]>([])
const loadState = createLoadState<RecycleBinEntry[]>([])
const loading = ref(false)
const selectedId = ref<number | null>(null)
const viewMode = ref<'grid' | 'list'>('grid')
const sortColumn = ref<'name' | 'date' | 'type' | 'size'>('date')
const sortDirection = ref<'asc' | 'desc'>('desc')
const searchKeyword = ref('')

const handleRefresh = () => void loadList()

onMounted(() => {
  canWrite.value = isEditorOrAbove.value
  void loadList()
  emitter.on('refresh:file-list', handleRefresh)
})

onBeforeUnmount(() => {
  emitter.off('refresh:file-list', handleRefresh)
})

function mapToFileEntry(item: RecycleBinEntry): FileEntry {
  return {
    id: item.id,
    file_name: item.name,
    is_folder: item.item_type === 'folder',
    format: item.format ?? null,
    created_at: item.deleted_at,
    file_size: item.size ?? 0,
    storage_path: null,
  }
}

const fileEntries = computed(() => items.value.map(mapToFileEntry))
const folders = computed(() => fileEntries.value.filter(f => f.is_folder))
const files = computed(() => fileEntries.value.filter(f => !f.is_folder))

const sortedFileEntries = computed(() => {
  const list = [...fileEntries.value]
  const dir = sortDirection.value === 'asc' ? 1 : -1
  list.sort((a, b) => {
    let cmp = 0
    switch (sortColumn.value) {
      case 'name': cmp = a.file_name.localeCompare(b.file_name); break
      case 'date': cmp = a.created_at.localeCompare(b.created_at); break
      case 'type': cmp = (a.format || '').localeCompare(b.format || ''); break
      case 'size': cmp = a.file_size - b.file_size; break
    }
    return cmp * dir
  })
  return list
})

const selectedFileEntry = computed(() => {
  if (selectedId.value === null) return null
  return fileEntries.value.find(item => item.id === selectedId.value) || null
})

function displayName(file: FileEntry): string {
  return file.is_folder ? String(file.file_name || '') : formatFileDisplayName(file.file_name, file.format)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

async function loadList() {
  loading.value = true
  startLoading(loadState)
  try {
    const nextItems = await fetchRecycleBinList() || []
    items.value = nextItems
    finishLoading(loadState, nextItems)
  } catch (error: unknown) {
    failLoading(loadState, error, '回收站加载失败')
  }
  finally { loading.value = false; selectedId.value = null }
}

function handleSelect(item: FileEntry) {
  selectedId.value = item.id
}

function handleOpen() {
  feedback.info('请先还原再打开文件')
}

function handleSort(column: string) {
  if (sortColumn.value === column) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column as 'name' | 'date' | 'type' | 'size'
    sortDirection.value = 'asc'
  }
}

async function emptyTrash() {
  if (!(await feedback.confirm('确定清空回收站？', '确认', { tone: 'warning' }))) return
  try { await emptyRecycleBinRequest(); feedback.success('已清空'); void loadList() }
  catch { feedback.warning('清空失败') }
}

function handleBlankMenu(e: MouseEvent) {
  emit('context-menu-blank', e, items.value.length > 0 && canWrite.value ? [
    { key: 'empty-recycle-bin', label: '清空回收站', icon: '🧹', danger: true },
    { key: 'refresh', label: '刷新', icon: '↻' },
  ] : [
    { key: 'refresh', label: '刷新', icon: '↻' },
  ])
}

function handleItemContextMenu(fileEntry: FileEntry, event: MouseEvent) {
  const originalItem = items.value.find(item => item.id === fileEntry.id)
  if (!originalItem) return
  emit('context-menu-item', event, originalItem, canWrite.value ? [
    { key: 'restore', label: '还原', icon: '↩' },
    { key: 'delete-permanently', label: '彻底删除', icon: '🗑', danger: true },
  ] : [])
}
</script>

<style scoped>
.fm-recycle-view { height: 100%; display: flex; flex-direction: column; background: #f8fafc; }
.rv-toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #dbe4ee; background: #f1f5f9; flex-shrink: 0; }
.rv-title { flex: 1; font-weight: 600; font-size: 14px; color: #1f2937; }
</style>
