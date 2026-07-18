<template>
  <footer class="fm-status-bar">
    <div class="fm-status-left">
      <template v-if="searchKeyword">
        找到 {{ filteredCount }} 个结果
      </template>
      <template v-else>
        <span>{{ itemCount }} 个项目</span>
        <span v-if="selectedItem">· 已选择 {{ displayName(selectedItem) }}</span>
        <span v-if="selectedItem && !selectedItem.is_folder">({{ selectedSize }})</span>
      </template>
    </div>
    <div v-if="viewMode === 'grid' || viewMode === 'gallery'" class="fm-status-right">
      <span class="fm-icon-size-label">图标大小</span>
      <input
        class="fm-icon-size"
        type="range"
        min="36"
        max="72"
        step="2"
        :value="iconSize"
        aria-label="图标大小"
        @input="$emit('update:iconSize', Number(($event.target as HTMLInputElement).value))"
      />
    </div>
  </footer>
</template>

<script setup lang="ts">
import type { FileEntry } from '@/shared/api/types'

defineProps<{
  itemCount: number
  folderCount: number
  fileCount: number
  selectedItem: FileEntry | null
  selectedSize: string
  viewMode: 'grid' | 'list' | 'column' | 'gallery'
  searchKeyword: string
  filteredCount: number
  displayName: (file: FileEntry) => string
  iconSize: number
}>()

defineEmits<{
  (e: 'update:viewMode', mode: 'grid' | 'list' | 'column' | 'gallery'): void
  (e: 'update:iconSize', size: number): void
}>()
</script>

<style scoped>
.fm-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 22px;
  min-height: 22px;
  padding: 0 12px;
  box-sizing: border-box;
  font: 400 11px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: var(--mac-app-text-secondary, #6e6e73);
  background: transparent;
  box-shadow: inset 0 0.5px 0 var(--mac-app-border, rgba(60, 60, 67, 0.16));
}

.fm-status-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.fm-status-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.fm-icon-size-label {
  font-size: 10px;
  color: color-mix(in srgb, var(--mac-app-text-secondary, #6e6e73) 88%, transparent);
}

.fm-icon-size {
  width: 110px;
  height: 14px;
  accent-color: var(--mac-app-accent, #0a84ff);
  cursor: pointer;
}
</style>
