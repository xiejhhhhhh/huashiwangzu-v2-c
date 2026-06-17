<template>
  <div class="desktop-file-manager" @contextmenu.prevent="handleBlankContextMenu" @click="ctxVisible = false">
    <div class="fm-toolbar">
      <el-button size="small" :icon="ArrowLeft" :disabled="!canGoUp" @click="goUp">上级</el-button>
      <span class="fm-breadcrumb">{{ breadcrumbText }}</span>
      <el-button size="small" :icon="Refresh" @click="loadFiles">刷新</el-button>
      <el-button size="small" :icon="Upload" :disabled="!canWrite" @click="triggerUpload">上传</el-button>
      <el-button size="small" :icon="FolderAdd" :disabled="!canWrite" @click="createFolder">新建文件夹</el-button>
      <input ref="uploadInput" type="file" style="display:none" @change="onUploadFile" />
    </div>
    <div v-if="loading" class="fm-loading">加载中...</div>
    <div v-else-if="items.length === 0" class="fm-empty">此文件夹为空</div>
    <div v-else class="fm-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="fm-item"
        :class="{ 'fm-item-folder': item.is_folder }"
        @dblclick="openItem(item)"
        @contextmenu.prevent.stop="handleItemMenu(item, $event)"
      >
        <span class="fm-item-icon">{{ item.is_folder ? '📁' : '📄' }}</span>
        <span class="fm-item-name">{{ item.is_folder ? item.file_name : (item.file_name + (item.format ? '.' + item.format : '')) }}</span>
        <span class="fm-item-size">{{ item.is_folder ? '' : formatSize(item.file_size) }}</span>
      </div>
    </div>
    <div v-if="ctxVisible" class="ctx-overlay" @click.self="ctxVisible = false">
      <div class="ctx-menu" :style="{ left: ctxX + 'px', top: ctxY + 'px' }">
        <div v-for="mi in ctxItems" :key="mi.key" class="ctx-item" :class="{ 'ctx-danger': mi.danger, 'ctx-disabled': mi.disabled }" @click="handleCtxClick(mi.key)">
          <span class="ctx-icon">{{ mi.icon || '' }}</span>
          <span class="ctx-label">{{ mi.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Refresh, Upload, FolderAdd } from '@element-plus/icons-vue'
import { fetchFileList, uploadFileRequest, renameEntryRequest, moveToRecycleBinRequest, createFileRequest } from '@/shared/api/desktop'
import { openFileByRecord } from '@/desktop/app-registry/app-opener'
import { buildFileMenu, buildFolderMenu } from '@/desktop/context-menu/file-context-menu'
import type { FileEntry } from '@/shared/api/types'
import api from '@/shared/api'
import { usePermission } from '@/shared/composables/use-permission'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'

defineProps<{ payload?: Record<string, unknown> }>()

const { isEditorOrAbove } = usePermission()
const canWrite = computed(() => isEditorOrAbove.value)
const { creatableFormats } = useCreatableFormats()

const currentFolderId = ref<number>(0)
const items = ref<FileEntry[]>([])
const loading = ref(false)
const uploadInput = ref<HTMLInputElement>()
const breadcrumb = ref<Array<{ id: number | null; name: string }>>([{ id: null, name: '桌面' }])
const breadcrumbText = computed(() => breadcrumb.value.map(b => b.name).join(' / '))
const canGoUp = computed(() => breadcrumb.value.length > 1)

const ctxVisible = ref(false)
const ctxX = ref(0)
const ctxY = ref(0)
const ctxItems = ref<Array<{ key: string; label: string; icon?: string; disabled?: boolean; danger?: boolean }>>([])
let ctxTarget: FileEntry | null = null

onMounted(() => { void loadFiles() })

async function loadFiles() {
  loading.value = true
  try { const res = await fetchFileList(currentFolderId.value); if (res.success) items.value = res.data?.items || [] }
  finally { loading.value = false }
}

async function goUp() {
  if (breadcrumb.value.length > 1) { breadcrumb.value.pop(); const p = breadcrumb.value[breadcrumb.value.length - 1]; currentFolderId.value = p.id ?? 0; await loadFiles() }
}

function openItem(item: FileEntry) {
  if (item.is_folder) { breadcrumb.value.push({ id: item.id, name: item.file_name }); currentFolderId.value = item.id; void loadFiles() }
  else { openFileByRecord({ fileId: item.id, fileName: item.file_name, format: item.format || '' }) }
}

function triggerUpload() { uploadInput.value?.click() }

async function onUploadFile(e: Event) {
  const input = e.target as HTMLInputElement; const file = input.files?.[0]
  if (!file) return
  try { await uploadFileRequest(file, currentFolderId.value || undefined); ElMessage.success('上传成功'); input.value = ''; await loadFiles() }
  catch { ElMessage.warning('上传失败') }
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value) return
    await api.post('/files/folder', { name: value, parent_id: currentFolderId.value || null })
    ElMessage.success('已创建'); await loadFiles()
  } catch { /* cancelled */ }
}

function showMenu(items: Array<{ key: string; label: string; icon?: string; disabled?: boolean; danger?: boolean }>, e: MouseEvent) {
  ctxItems.value = items; ctxX.value = e.clientX; ctxY.value = e.clientY; ctxVisible.value = true
}

function handleBlankContextMenu(e: MouseEvent) {
  ctxTarget = null
  const items = [
    { key: 'refresh', label: '刷新', icon: '↻' },
    { key: 'upload-file', label: '上传', icon: '⬆', disabled: !canWrite.value },
    { key: 'create-folder', label: '新建文件夹', icon: '+', disabled: !canWrite.value },
  ]
  if (canWrite.value && creatableFormats.value.length) {
    items.push({ key: 'new-file', label: '新建文件', icon: '📄', disabled: false, children: creatableFormats.value.map(f => ({ key: `create-file:${f.extension}`, label: f.label, icon: '' })) } as never)
  }
  showMenu(items, e)
}

function handleItemMenu(item: FileEntry, e: MouseEvent) {
  ctxTarget = item
  let menu
  if (item.is_folder) {
    menu = buildFolderMenu(canWrite.value, () => []) as Array<{ key: string; label: string; icon?: string; disabled?: boolean; danger?: boolean }>
    if (canWrite.value && creatableFormats.value.length) {
      menu.splice(3, 0, { key: 'new-file', label: '新建文件', icon: '📄', disabled: false } as never)
    }
  } else {
    menu = buildFileMenu(canWrite.value, () => []) as Array<{ key: string; label: string; icon?: string; disabled?: boolean; danger?: boolean }>
  }
  showMenu(menu, e)
}

async function handleCtxClick(key: string) {
  ctxVisible.value = false; const file = ctxTarget
  if (key === 'refresh') { await loadFiles(); return }
  if (key === 'upload-file') { triggerUpload(); return }
  if (key === 'create-folder') { await createFolder(); return }
  if (key.startsWith('create-file:')) { const ext = key.slice('create-file:'.length); const fmt = creatableFormats.value.find(f => f.extension === ext); const label = fmt?.label || `.${ext}`; try { await createFileRequest(label, ext, currentFolderId.value || null); ElMessage.success(`已创建 ${label}`); await loadFiles() } catch { ElMessage.warning('创建失败') }; return }
  if (!file) return
  if (key === 'open') { openItem(file); return }
  if (key === 'download') {
    try { const res = await api.get(`/files/download/${file.id}`, { responseType: 'blob' }); const url = URL.createObjectURL(res.data); const a = document.createElement('a'); a.href = url; a.download = file.format ? `${file.file_name}.${file.format}` : file.file_name; a.click(); URL.revokeObjectURL(url) } catch { ElMessage.warning('下载失败') }
    return
  }
  if (key === 'copy-path') { const p = file.format ? `${file.file_name}.${file.format}` : file.file_name; try { await navigator.clipboard.writeText(p); ElMessage.success('已复制') } catch { /* */ } return }
  if (key === 'rename') {
    try { const { value } = await ElMessageBox.prompt('新名称', '重命名', { inputValue: file.file_name }); if (value && value !== file.file_name) { await renameEntryRequest(file.is_folder ? 'folder' : 'file', file.id, value); ElMessage.success('已重命名'); await loadFiles() } } catch { /* */ }
    return
  }
  if (key === 'delete') { try { await ElMessageBox.confirm('确定删除？', '确认', { type: 'warning' }) } catch { return }; await moveToRecycleBinRequest(file.is_folder ? 'folder' : 'file', file.id); ElMessage.success('已删除'); await loadFiles(); return }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}
</script>

<style scoped>
.desktop-file-manager { height: 100%; display: flex; flex-direction: column; background: #fff; }
.fm-toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #eee; flex-shrink: 0; }
.fm-breadcrumb { flex: 1; font-size: 13px; color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fm-loading, .fm-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; }
.fm-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.fm-item { display: flex; align-items: center; padding: 6px 16px; cursor: pointer; user-select: none; }
.fm-item:hover { background: #f0f5ff; }
.fm-item-icon { width: 28px; font-size: 18px; text-align: center; }
.fm-item-name { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fm-item-size { font-size: 12px; color: #999; margin-left: 12px; }
.ctx-overlay { position: fixed; inset: 0; z-index: 9999; }
.ctx-menu { position: fixed; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; box-shadow: 0 2px 12px rgba(0,0,0,.12); padding: 4px 0; min-width: 140px; }
.ctx-item { display: flex; align-items: center; gap: 8px; padding: 6px 16px; font-size: 13px; cursor: pointer; }
.ctx-item:hover { background: #ecf5ff; }
.ctx-disabled { color: #c0c4cc; cursor: not-allowed; pointer-events: none; }
.ctx-danger { color: #f56c6c; }
.ctx-icon { width: 20px; text-align: center; }
</style>
