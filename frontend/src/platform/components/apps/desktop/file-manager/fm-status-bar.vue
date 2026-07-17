<template>
  <footer class="fm-status-bar">
    <div class="fm-status-left">
      <template v-if="searchKeyword">
        找到 {{ filteredCount }} 个结果
      </template>
      <template v-else>
        <span>{{ itemCount }} 个项目</span>
        <span v-if="selectedItem">已选择 {{ displayName(selectedItem) }}</span>
        <span v-if="selectedItem && !selectedItem.is_folder">({{ selectedSize }})</span>
      </template>
    </div>
    <div class="fm-status-right">
      <button
        class="fm-view-btn"
        :class="{ 'fm-view-btn-active': viewMode === 'list' }"
        type="button"
        title="列表"
        @click="$emit('update:viewMode', 'list')"
      >
        <List :size="15" :stroke-width="2" />
      </button>
      <button
        class="fm-view-btn"
        :class="{ 'fm-view-btn-active': viewMode === 'grid' }"
        type="button"
        title="图标"
        @click="$emit('update:viewMode', 'grid')"
      >
        <Grid3X3 :size="14" :stroke-width="2" />
      </button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { Grid3X3, List } from 'lucide-vue-next'
import type { FileEntry } from '@/shared/api/types'

defineProps<{
  itemCount: number
  folderCount: number
  fileCount: number
  selectedItem: FileEntry | null
  selectedSize: string
  viewMode: 'grid' | 'list'
  searchKeyword: string
  filteredCount: number
  displayName: (file: FileEntry) => string
}>()

defineEmits<{
  (e: 'update:viewMode', mode: 'grid' | 'list'): void
}>()
</script>

<style scoped>
.fm-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 29px;
  padding: 0 14px;
  border-top: 1px solid rgba(60, 60, 67, 0.16);
  background: rgba(246, 246, 246, 0.88);
  font-size: 12px;
  color: #6e6e73;
}

.fm-status-left {
  display: flex;
  align-items: center;
  gap: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fm-status-right {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 2px;
  border-radius: 6px;
  background: rgba(60, 60, 67, 0.1);
  flex-shrink: 0;
}

.fm-view-btn {
  width: 27px;
  height: 21px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: #626267;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.fm-view-btn:hover {
  background: rgba(255, 255, 255, 0.6);
}

.fm-view-btn-active {
  color: #1d1d1f;
  background: #fff;
  border-color: rgba(60, 60, 67, 0.1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.16);
}
</style>
