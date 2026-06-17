<template>
  <div class="recycle-bin-container">
    <div class="recycle-bin-toolbar">
      <el-button size="small" @click="handleClose"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
      <span class="recycle-bin-title">回收站</span>
      <span style="flex:1" />
      <el-button v-if="canWrite" size="small" type="danger" plain @click="emit('clear')" :disabled="items.length === 0">
        <el-icon><Delete /></el-icon> 清空回收站
      </el-button>
    </div>
    <div class="recycle-bin-list" v-loading="loading" @contextmenu.prevent>
      <el-table :data="items" stripe size="small" style="width:100%" empty-text="回收站是空的" @row-contextmenu="handleRowContextMenu">
        <el-table-column label="名称" min-width="200">
          <template #default="{ row }">
            <div class="filename-cell">
              <el-icon><Document v-if="row.item_type === 'file'" /><Folder v-else /></el-icon>
              {{ row.name }}<span v-if="row.format">.{{ row.format }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="item_type" label="类型" width="80" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ row.item_type === 'file' ? formatSize(row.size) : '-' }}</template>
        </el-table-column>
        <el-table-column prop="deleted_at" label="删除时间" width="180" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canWrite" link type="primary" size="small" @click="emit('restore', row.item_type, row.id)">还原</el-button>
            <el-button v-if="canWrite" link type="danger" size="small" @click="emit('delete-permanently', row.item_type, row.id)">彻底删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Delete, Document, Folder } from '@element-plus/icons-vue'
import { usePermission } from '@/shared/composables/use-permission'
import type { RecycleBinEntry } from '@/shared/api/types'

defineProps<{
  items: RecycleBinEntry[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'restore', itemType: 'file' | 'folder', id: number): void
  (e: 'delete-permanently', itemType: 'file' | 'folder', id: number): void
  (e: 'clear'): void
  (e: 'row-contextmenu', row: RecycleBinEntry, column: unknown, event: MouseEvent): void
}>()

function handleRowContextMenu(row: RecycleBinEntry, column: unknown, event: MouseEvent) {
  emit('row-contextmenu', row, column, event)
}

const { isEditorOrAbove: canWrite } = usePermission()

function handleClose() {
  emit('close')
}

function formatSize(bytes?: number | null): string {
  if (!bytes || bytes === 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`
}
</script>

<style scoped>
.recycle-bin-container { display: flex; flex-direction: column; height: 100%; }
.recycle-bin-toolbar { padding: 12px 16px; border-bottom: 1px solid #e4e7ed; display: flex; align-items: center; gap: 8px; }
.recycle-bin-title { font-size: 14px; font-weight: 600; color: #303133; }
.recycle-bin-list { flex: 1; overflow-y: auto; }
.filename-cell { display: flex; align-items: center; gap: 6px; }
</style>
