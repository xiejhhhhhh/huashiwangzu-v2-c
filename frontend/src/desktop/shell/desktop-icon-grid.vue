<template>
  <div class="desktop-icon-grid">
    <div
      v-for="app in appList"
      :key="app.appKey"
      class="desktop-icon-item desktop-app-icon-item"
      :class="{ 'desktop-icon-item-selected': isSelected(`app:${app.appKey}`) }"
      :data-selection-key="`app:${app.appKey}`"
      :style="getIconStyle(`app:${app.appKey}`)"
      @mousedown.stop="handleIconMouseDown(`app:${app.appKey}`, $event)"
      @click="handleAppClick(app.appKey, $event)"
      @dblclick="$emit('openApp', app.appKey)"
      @contextmenu.prevent.stop="$emit('app-context-menu', app.appKey, $event)"
    >
      <div class="desktop-icon-image">
        <AppIcon :icon="app.icon" :size="54" />
      </div>
      <span class="desktop-icon-label">{{ app.appName }}</span>
    </div>
    <div
      v-for="file in fileList"
      :key="`file-${file.id}`"
      class="desktop-icon-item desktop-file-icon-item"
      :class="{
        'desktop-icon-item-selected': isSelected(`file:${file.id}`),
        'desktop-icon-item-drag-over': file.is_folder && dragState.dragOverId === String(file.id),
      }"
      :data-selection-key="`file:${file.id}`"
      :data-folder="file.is_folder ? String(file.id) : undefined"
      :style="getIconStyle(`file:${file.id}`)"
      @mousedown.stop="handleIconMouseDown(`file:${file.id}`, $event)"
      @click="handleFileClick(file, $event)"
      @dblclick="$emit('openFile', file)"
      @contextmenu.prevent.stop="$emit('file-context-menu', file, $event)"
    >
      <div class="desktop-icon-image">
        <FileVisualIcon :kind="file.is_folder || !file.format ? 'folder' : 'file'" :extension="file.format || ''" :size="48" />
      </div>
      <span class="desktop-icon-label">{{ getFileName(file) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import type { FileEntry } from '@/shared/api/types'
import AppIcon from '@/desktop/components/app-icon.vue'
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import { isSelected, select, appendSelection, selectedIds } from '@/desktop/selection/desktop-selection-state'
import { nextTick, onMounted, watch } from 'vue'
import { formatFileDisplayName } from '@/shared/files/display-name'
import { startDrag, dragState } from '@/desktop/drag-drop/drag-state'
import { getDropOverlayStyle, restorePersistedIconPositions } from '@/desktop/drag-drop/drag-tool'
import './desktop-icon-grid.css'

const props = defineProps<{
  appList: AppRegistryEntry[]
  fileList?: FileEntry[]
}>()

const emit = defineEmits<{
  (e: 'openApp', appKey: string): void
  (e: 'openFile', file: FileEntry): void
  (e: 'app-context-menu', appKey: string, event: MouseEvent): void
  (e: 'file-context-menu', file: FileEntry, event: MouseEvent): void
}>()

let suppressNextClick = false
let pendingDrag: { key: string; startX: number; startY: number } | null = null

async function restoreIconPositionsAfterRender(): Promise<void> {
  await nextTick()
  restorePersistedIconPositions()
}

onMounted(() => {
  void restoreIconPositionsAfterRender()
})

watch(() => [props.appList, props.fileList], () => {
  void restoreIconPositionsAfterRender()
}, { deep: true })


function getIconStyle(key: string): { transform?: string } {
  const transform = getDropOverlayStyle(key)
  return transform ? { transform } : {}
}

function handleIconMouseDown(key: string, e: MouseEvent) {
  if (e.button !== 0) return
  pendingDrag = { key, startX: e.clientX, startY: e.clientY }
  document.addEventListener('mousemove', handlePendingDragMove)
  document.addEventListener('mouseup', clearPendingDrag)
}

function handlePendingDragMove(e: MouseEvent) {
  if (!pendingDrag) return
  const dx = e.clientX - pendingDrag.startX
  const dy = e.clientY - pendingDrag.startY
  if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return
  const shouldDragSelection = selectedIds.value.includes(pendingDrag.key) && (e.ctrlKey || e.shiftKey)
  const dragIds = shouldDragSelection ? selectedIds.value : [pendingDrag.key]
  if (!selectedIds.value.includes(pendingDrag.key)) select(pendingDrag.key)
  suppressNextClick = true
  startDrag(dragIds, pendingDrag.startX, pendingDrag.startY)
  clearPendingDrag()
}

function clearPendingDrag() {
  document.removeEventListener('mousemove', handlePendingDragMove)
  document.removeEventListener('mouseup', clearPendingDrag)
  pendingDrag = null
}

function handleAppClick(appKey: string, e: MouseEvent) {
  if (suppressNextClick || dragState.isDragging) { suppressNextClick = false; return }
  const key = `app:${appKey}`
  if (e.ctrlKey) { appendSelection(key); return }
  if (isSelected(key)) return
  select(key)
}

function handleFileClick(file: FileEntry, e: MouseEvent) {
  if (suppressNextClick || dragState.isDragging) { suppressNextClick = false; return }
  const key = `file:${file.id}`
  if (e.ctrlKey) { appendSelection(key); return }
  if (isSelected(key)) return
  select(key)
}

function getFileName(file: FileEntry) {
  return file.is_folder ? String(file.file_name || '') : formatFileDisplayName(file.file_name, file.format)
}
</script>
