<template>
  <div class="recycle-app" @contextmenu.prevent="handleBlankMenu" @click="ctxVisible = false">
    <div class="ra-toolbar">
      <span class="ra-title">回收站</span>
      <el-button size="small" :icon="Refresh" @click="loadList">刷新</el-button>
      <el-button size="small" :disabled="!canWrite || items.length === 0" @click="emptyTrash">清空回收站</el-button>
    </div>
    <div v-if="loading" class="ra-loading">加载中...</div>
    <div v-else-if="items.length === 0" class="ra-empty">回收站为空</div>
    <div v-else class="ra-list">
      <div v-for="item in items" :key="item.id" class="ra-item" @contextmenu.prevent.stop="handleItemMenu(item, $event)">
        <span class="ra-item-icon">{{ item.item_type === 'folder' ? '📁' : '📄' }}</span>
        <span class="ra-item-name">{{ item.name }}</span>
        <span class="ra-item-date">{{ formatDate(item.deleted_at) }}</span>
        <template v-if="canWrite">
          <el-button size="small" text type="primary" @click="restoreItem(item)">还原</el-button>
          <el-button size="small" text type="danger" @click="permanentDelete(item)">彻底删除</el-button>
        </template>
      </div>
    </div>
    <div v-if="ctxVisible" class="ctx-overlay" @click.self="ctxVisible = false">
      <div class="ctx-menu" :style="{ left: ctxX + 'px', top: ctxY + 'px' }">
        <div v-for="mi in ctxItems" :key="mi.key" class="ctx-item" :class="{ 'ctx-danger': mi.danger }" @click="handleCtxClick(mi.key)">
          <span class="ctx-icon">{{ mi.icon || '' }}</span>
          <span class="ctx-label">{{ mi.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { fetchRecycleBinList, restoreRecycleBinEntry, permanentlyDeleteEntry, emptyRecycleBinRequest } from '@/shared/api/desktop'
import { buildRecycleBinItemMenu } from '@/desktop/context-menu/file-context-menu'
import type { RecycleBinEntry } from '@/shared/api/types'
import { usePermission } from '@/shared/composables/use-permission'

const { isEditorOrAbove } = usePermission()
const canWrite = ref(false)
const items = ref<RecycleBinEntry[]>([])
const loading = ref(false)

const ctxVisible = ref(false)
const ctxX = ref(0)
const ctxY = ref(0)
const ctxItems = ref<Array<{ key: string; label: string; icon?: string; danger?: boolean }>>([])
let ctxItem: RecycleBinEntry | null = null

onMounted(() => { canWrite.value = isEditorOrAbove.value; void loadList() })

async function loadList() {
  loading.value = true
  try { const res = await fetchRecycleBinList(); if (res.success) items.value = res.data || [] }
  finally { loading.value = false }
}

async function restoreItem(item: RecycleBinEntry) {
  try { await restoreRecycleBinEntry(item.item_type, item.id); ElMessage.success('已还原'); await loadList() }
  catch { ElMessage.warning('还原失败') }
}

async function permanentDelete(item: RecycleBinEntry) {
  try { await ElMessageBox.confirm('确定彻底删除？', '确认', { type: 'warning' }) } catch { return }
  try { await permanentlyDeleteEntry(item.item_type, item.id); ElMessage.success('已删除'); await loadList() }
  catch { ElMessage.warning('删除失败') }
}

async function emptyTrash() {
  try { await ElMessageBox.confirm('确定清空回收站？', '确认', { type: 'warning' }) } catch { return }
  try { await emptyRecycleBinRequest(); ElMessage.success('已清空'); await loadList() }
  catch { ElMessage.warning('清空失败') }
}

function handleBlankMenu(e: MouseEvent) {
  ctxItem = null; ctxItems.value = []
  if (items.value.length > 0 && canWrite.value) {
    ctxItems.value = [{ key: 'empty-recycle-bin', label: '清空回收站', icon: '🧹', danger: true }]
  }
  ctxX.value = e.clientX; ctxY.value = e.clientY; ctxVisible.value = true
}

function handleItemMenu(item: RecycleBinEntry, e: MouseEvent) {
  ctxItem = item; ctxItems.value = buildRecycleBinItemMenu(canWrite.value)
  ctxX.value = e.clientX; ctxY.value = e.clientY; ctxVisible.value = true
}

async function handleCtxClick(key: string) {
  ctxVisible.value = false
  if (key === 'restore' && ctxItem) await restoreItem(ctxItem)
  if (key === 'delete-permanently' && ctxItem) await permanentDelete(ctxItem)
  if (key === 'empty-recycle-bin') await emptyTrash()
}

function formatDate(d: string): string {
  try { return new Date(d).toLocaleString() } catch { return d }
}
</script>

<style scoped>
.recycle-app { height: 100%; display: flex; flex-direction: column; background: #fff; }
.ra-toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #eee; flex-shrink: 0; }
.ra-title { flex: 1; font-weight: 600; font-size: 14px; }
.ra-loading, .ra-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; }
.ra-list { flex: 1; overflow-y: auto; }
.ra-item { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid #f5f5f5; }
.ra-item:hover { background: #fafafa; }
.ra-item-icon { font-size: 18px; }
.ra-item-name { flex: 1; font-size: 13px; }
.ra-item-date { font-size: 12px; color: #999; min-width: 140px; }
.ctx-overlay { position: fixed; inset: 0; z-index: 9999; }
.ctx-menu { position: fixed; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; box-shadow: 0 2px 12px rgba(0,0,0,.12); padding: 4px 0; min-width: 140px; }
.ctx-item { display: flex; align-items: center; gap: 8px; padding: 6px 16px; font-size: 13px; cursor: pointer; }
.ctx-item:hover { background: #ecf5ff; }
.ctx-danger { color: #f56c6c; }
.ctx-icon { width: 20px; text-align: center; }
</style>
