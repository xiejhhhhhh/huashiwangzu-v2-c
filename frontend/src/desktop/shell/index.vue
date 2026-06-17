<template>
  <div ref="desktopContainerRef" class="desktop-shell-container" @contextmenu.prevent="handleDesktopContextMenu" @mousedown="handleDesktopMouseDown" @dragover.prevent="onDragEnter" @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
    <div class="desktop-shell-wallpaper" :style="{ backgroundImage: `url(${wallpaper})` }" />
    <div class="desktop-shell-icon-layer">
      <component :is="desktopIconGrid" :app-list="desktopAppList" :file-list="desktopFileList" @openApp="handleOpenApp" @openFile="openDesktopEntry" @app-context-menu="handleAppContextMenu" @file-context-menu="handleFileContextMenu" />
      <SelectionBox />
    </div>
    <component
      :is="desktopWindowFrame"
      v-for="w in windowManager.windows"
      :key="w.id"
      :id="w.id"
      :title="w.title"
      :icon="w.icon"
      :x="w.x"
      :y="w.y"
      :width="w.width"
      :height="w.height"
      :z-index="w.zIndex"
      :minimized="w.minimized"
      :maximized="w.maximized"
      :is-active="w.isActive"
      :app-key="w.appKey"
      :payload="w.payload"
      @activate="windowManager.activateWindow"
      @close="windowManager.closeWindow"
      @minimize="windowManager.toggleMinimized"
      @maximize="windowManager.toggleMaximized"
      @update-position="windowManager.updateWindowPosition"
      @update-geometry="windowManager.updateWindowGeometry"
    />
    <component :is="desktopTaskbar" :items="unref(windowManager.taskbarItems)" :launcher-open="showLauncher" :tray-apps="trayAppList" @switchWindow="handleSwitchWindow" @openLauncher="showLauncher = !showLauncher" @openTrayApp="windowManager.openWindow" />
    <component :is="desktopLauncher" v-if="showLauncher" :show="showLauncher" :app-list="launcherAppList" @openApp="handleLauncherOpen" @execute-command="handleLauncherCommand" @close="showLauncher = false" />
    <component :is="desktopRightSidebar" :show="showRightSidebar" :current-path="rightSidebarPath" :current-app-key="rightSidebarAppKey" :app-list="sidebarAppList" @close="showRightSidebar = false" @switch="openSidebar" @open-window="handleOpenApp" />
    <ContextMenu
      :visible="contextMenu.visible.value"
      :x="contextMenu.x.value"
      :y="contextMenu.y.value"
      :context-type="contextMenu.context.value?.type"
      :current-items="contextMenu.currentItems.value"
      :active-submenu="contextMenu.activeSubmenu.value"
      :open-submenu="contextMenu.openSubmenu"
      :close-submenu="contextMenu.closeSubmenu"
      :keep-submenu-open="contextMenu.keepSubmenuOpen"
      @select="handleContextMenuSelect"
    />
    <div v-if="registryError" class="desktop-shell-error">
       <p>{{ registryError }}</p>
       <button @click="retryLoadRegistry">重试</button>
     </div>
     <div v-else-if="!windowManager.openedWindowCount" class="desktop-shell-hint">
       双击图标打开应用 · 右键管理文件与回收站
     </div>
     <div v-if="isDragActive" class="desktop-shell-drop-hint">松开后上传到桌面</div>
     <div v-if="loading" class="desktop-shell-loading">加载中...</div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, computed, unref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useContextMenu } from '@/desktop/context-menu/use-context-menu'
import ContextMenu from '@/desktop/context-menu/context-menu.vue'
import { useWindowManager } from '@/desktop/window-manager/window-manager'
import { getApp } from '@/desktop/app-registry/app-registry'
import { usePermission } from '@/shared/composables/use-permission'
import { useUserStore } from '@/platform/stores/user'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import SelectionBox from '@/desktop/selection/SelectionBox.vue'
import { useDesktopShellDropUpload } from './use-desktop-shell-drop-upload'
import { useDesktopRootFiles } from './use-desktop-root-files'
import { useDesktopAppLoading } from './use-desktop-app-loading'
import { useDesktopPointer } from './use-desktop-pointer'
import { buildFileMenu, buildFolderMenu } from '@/desktop/context-menu/file-context-menu'
import { buildDesktopShellIconMenu as buildAppIconMenu, buildDesktopShellBlankMenu } from '@/desktop/context-menu/desktop-shell-context-menu'
import { buildRecycleBinMenu, buildRecycleBinItemMenu } from '@/desktop/context-menu/file-context-menu'
import { copyItems, cutItems, hasContent, currentClipboardType, currentClipboardItems, clearClipboard, getClipboardIdList } from '@/desktop/clipboard/clipboard-state'
import type { ClipboardItem } from '@/desktop/clipboard/clipboard-state'
import {
  renameEntryRequest, moveEntryRequest, copyEntryRequest, moveToRecycleBinRequest,
  createFileRequest, uploadFileRequest, restoreRecycleBinEntry, permanentlyDeleteEntry,
  emptyRecycleBinRequest, fetchRecycleBinList
} from '@/shared/api/desktop'
import type { FileEntry } from '@/shared/api/types'
import api from '@/shared/api'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'

const desktopIconGrid = defineAsyncComponent(() => import('@/desktop/shell/desktop-icon-grid.vue'))
const desktopWindowFrame = defineAsyncComponent(() => import('@/desktop/window-manager/desktop-window-frame.vue'))
const desktopTaskbar = defineAsyncComponent(() => import('@/desktop/taskbar/desktop-taskbar.vue'))
const desktopLauncher = defineAsyncComponent(() => import('@/desktop/launcher/desktop-launcher.vue'))
const desktopRightSidebar = defineAsyncComponent(() => import('@/desktop/shell/desktop-right-sidebar.vue'))
const windowManager = useWindowManager()
const { isEditorOrAbove: canBusinessWrite, currentRole } = usePermission()
const contextMenu = useContextMenu()
const userStore = useUserStore()
const { emit } = useDesktopEventBus()
const { isDragActive, onDragEnter, onDragLeave, onDrop } = useDesktopShellDropUpload()
const { desktopFileList, openDesktopEntry } = useDesktopRootFiles()
const { creatableFormats } = useCreatableFormats()
const { desktopAppList, launcherAppList, sidebarAppList, trayAppList, registryError, loading, desktopContainerRef, retryLoadRegistry, updateContainerSize } = useDesktopAppLoading(currentRole)
const { handleDesktopMouseDown } = useDesktopPointer()

const showLauncher = ref(false); const showRightSidebar = ref(false); const rightSidebarAppKey = ref('dashboard')
const canWrite = computed(() => canBusinessWrite.value)

const wallpaper = 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0f172a"/><stop offset="50%" stop-color="#1d4ed8"/><stop offset="100%" stop-color="#7c3aed"/></linearGradient><radialGradient id="r" cx="30%" cy="20%" r="60%"><stop offset="0%" stop-color="rgba(191,219,254,0.35)"/><stop offset="100%" stop-color="rgba(15,23,42,0)"/></radialGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><rect width="100%" height="100%" fill="url(#r)"/></svg>')

function handleOpenApp(appKey: string) { windowManager.openWindow(appKey) }
function openSidebar(appKey = 'dashboard') { rightSidebarAppKey.value = appKey; showRightSidebar.value = true }
function handleLauncherOpen(appKey: string) {
  showLauncher.value = false
  const app = getApp(appKey)
  if (app?.showInSidebar) openSidebar(appKey); else handleOpenApp(appKey)
}
async function handleLauncherCommand(command: string) {
  const { windows: ws, toggleMinimized: toggle } = windowManager
  if (command === 'open-sidebar') openSidebar('dashboard')
  else if (command === 'refresh-desktop') updateContainerSize()
  else if (command === 'logout') { await userStore.logout(); window.location.href = '/' }
  else if (command === 'minimize-all' || command === 'restore-all') ws.forEach((w: { id: string }) => toggle(w.id))
  showLauncher.value = false
}
function getSidebarPath(appKey: string): string { return '/' + appKey }

const rightSidebarPath = computed(() => getSidebarPath(rightSidebarAppKey.value))

// ── Context Menu: App Icons ──────────────────────────────────────────
function handleAppContextMenu(appKey: string, e: MouseEvent) {
  if (appKey === 'recycle') {
    const items = buildRecycleBinMenu(canWrite.value, () => [])
    if (!items.length) return
    contextMenu.open(e, items, { type: 'desktop-shell-icon', target: { appKey } })
    return
  }
  const items = buildAppIconMenu(appKey, canWrite.value, () => [])
  if (!items.length) return
  contextMenu.open(e, items, { type: 'desktop-shell-icon', target: { appKey } })
}

// ── Context Menu: Files & Folders ─────────────────────────────────────
function handleFileContextMenu(file: FileEntry, e: MouseEvent) {
  ctxtTarget.value = file
  let items: Array<{ key: string; label: string; icon?: string; disabled?: boolean; danger?: boolean; children?: Array<{ key: string; label: string; icon?: string }> }>
  if (file.is_folder) {
    items = buildFolderMenu(canWrite.value, () => []) as typeof items
    // Inject "新建文件" submenu for folders
    if (canWrite.value && creatableFormats.value.length) {
      items.splice(3, 0, { key: 'new-file', label: '新建文件', icon: '📄', children: creatableFormats.value.map(f => ({ key: `create-file:${f.extension}`, label: f.label, icon: '' })) })
    }
  } else {
    items = buildFileMenu(canWrite.value, () => []) as typeof items
  }
  contextMenu.open(e, items, { type: file.is_folder ? 'folder' : 'file', target: { ...file } })
}

// ── Context Menu: Desktop Blank ───────────────────────────────────────
function handleDesktopContextMenu(e: MouseEvent) {
  const el = e.target as HTMLElement
  if (el.closest('.desktop-window') || el.closest('.file-list-area')) return
  const base = buildDesktopShellBlankMenu(() => [])
  // Inject dynamic items
  if (canWrite.value && creatableFormats.value.length) {
    base.splice(2, 0, { key: 'new-file', label: '新建文件', icon: '📄', children: creatableFormats.value.map(f => ({ key: `create-file:${f.extension}`, label: f.label, icon: '' })) })
  }
  if (canWrite.value) {
    base.splice(canWrite.value && creatableFormats.value.length ? 3 : 2, 0, { key: 'upload-file', label: '上传文件', icon: '⬆' })
  }
  if (hasContent.value) {
    base.push({ key: 'paste', label: '粘贴', icon: '📌' })
  }
  contextMenu.open(e, base, { type: 'desktop-shell-blank' })
}

// Track file/folder currently being right-clicked
const ctxtTarget = ref<FileEntry | null>(null)

function getCtxtFile(): FileEntry | null { return ctxtTarget.value }

function refreshDesktop() {
  emit('refresh:file-list', { folderId: 0 })
  updateContainerSize()
}

// Inline file upload trigger
const uploadInputRef = ref<HTMLInputElement | null>(null)
let _pendingUploadFolderId: number | null = null

function triggerUpload(folderId: number | null) {
  _pendingUploadFolderId = folderId
  if (!uploadInputRef.value) {
    const input = document.createElement('input')
    input.type = 'file'
    input.style.display = 'none'
    input.addEventListener('change', onUploadSelected)
    document.body.appendChild(input)
    uploadInputRef.value = input
  }
  uploadInputRef.value.click()
}

async function onUploadSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    await uploadFileRequest(file, _pendingUploadFolderId ?? undefined)
    ElMessage.success('上传成功')
    input.value = ''
    refreshDesktop()
  } catch { ElMessage.warning('上传失败') }
}

async function createNewFolder(folderId: number | null) {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value) return
    await api.post('/files/folder', { name: value, parent_id: folderId })
    ElMessage.success('已创建')
    refreshDesktop()
  } catch { /* cancelled */ }
}

// ── Menu Action Handlers ──────────────────────────────────────────────
async function handleContextMenuSelect(menuKey: string) {
  contextMenu.close()
  const menuContext = contextMenu.context.value
  const appKey = (menuContext?.target?.appKey as string) || ''
  const file = menuContext?.target as FileEntry | undefined

  // Global / Desktop actions
  if (menuKey === 'refresh-desktop' || menuKey === 'refresh') { refreshDesktop(); return }
  if (menuKey === 'open-desktop-file-manager') { windowManager.openWindow('desktop'); return }
  if (menuKey === 'open-recycle-bin') { windowManager.openWindow('recycle'); return }
  if (menuKey === 'open-app' && appKey) { windowManager.openWindow(appKey); return }

  // Desktop blank: upload, create folder, paste
  if (menuKey === 'upload-file') { triggerUpload(null); return }
  if (menuKey === 'new-folder' || menuKey === 'create-folder') { await createNewFolder(null); return }
  if (menuKey === 'paste' && hasContent.value) { await pasteToFolder(null); return }

  // File actions
  if (file && file.id) {
    if (menuKey === 'open') { openDesktopEntry(file); return }
    if (menuKey === 'download') { await downloadFile(file); return }
    if (menuKey === 'preview') { windowManager.openWindow('filePreview', { fileId: file.id, fileName: file.file_name, format: file.format }); return }
    if (menuKey === 'copy-path') { await copyFilePath(file); return }
    if (menuKey === 'details') { await showFileDetails(file); return }
    if (menuKey === 'rename' && canWrite.value) { await renameFile(file); return }
    if (menuKey === 'delete' && canWrite.value) { await deleteFile(file); return }
    if (menuKey === 'cut' && canWrite.value) { cutItems([{ id: file.id, type: file.is_folder ? 'folder' as const : 'file' as const, name: file.file_name }]); ElMessage.success('已剪切'); return }
    if (menuKey === 'copy' && canWrite.value) { copyItems([{ id: file.id, type: file.is_folder ? 'folder' as const : 'file' as const, name: file.file_name }]); ElMessage.success('已复制'); return }
  }

  // Folder-specific actions
  if (file && file.is_folder) {
    if (menuKey === 'upload-here' && canWrite.value) { triggerUpload(file.id); return }
    if (menuKey === 'create-folder-here' && canWrite.value) { await createNewFolder(file.id); return }
    if (menuKey === 'paste-here' && canWrite.value && hasContent.value) { await pasteToFolder(file.id); return }
  }

  // Create file by extension
  if (menuKey.startsWith('create-file:') && canWrite.value) {
    const ext = menuKey.slice('create-file:'.length)
    const folderId = (file && file.is_folder) ? file.id : null
    const format = creatableFormats.value.find(f => f.extension === ext)
    const label = format?.label || `.${ext} 文件`
    try { await createFileRequest(label, ext, folderId); ElMessage.success(`已创建 ${label}`); refreshDesktop() }
    catch { ElMessage.warning('创建失败') }
    return
  }

  // Recycle actions
  if (menuKey === 'empty-recycle-bin' && canWrite.value) {
    try { await ElMessageBox.confirm('确定清空回收站？', '确认', { type: 'warning' }) } catch { return }
    await emptyRecycleBinRequest(); ElMessage.success('回收站已清空'); emit('refresh:file-list', { folderId: 0 }); return
  }
}

// ── File Operations ───────────────────────────────────────────────────
async function downloadFile(file: FileEntry) {
  try {
    const res = await api.get(`/files/download/${file.id}`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    const fullName = file.format ? `${file.file_name}.${file.format}` : file.file_name
    a.download = fullName
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.warning('下载失败') }
}

async function copyFilePath(file: FileEntry) {
  const fullName = file.format ? `${file.file_name}.${file.format}` : file.file_name
  try { await navigator.clipboard.writeText(fullName); ElMessage.success('已复制路径') }
  catch { ElMessage.warning('复制失败') }
}

async function showFileDetails(file: FileEntry) {
  const lines = [
    `名称: ${file.format ? file.file_name + '.' + file.format : file.file_name}`,
    `类型: ${file.is_folder ? '文件夹' : (file.format?.toUpperCase() || '文件')}`,
    `大小: ${file.is_folder ? '-' : formatSize(file.file_size)}`,
    `ID: ${file.id}`,
  ]
  if (file.created_at) lines.push(`创建时间: ${file.created_at}`)
  ElMessageBox.alert(lines.join('\n'), '属性')
}

async function renameFile(file: FileEntry) {
  try {
    const { value } = await ElMessageBox.prompt('输入新名称', '重命名', {
      inputValue: file.file_name,
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value || value === file.file_name) return
    await renameEntryRequest(file.is_folder ? 'folder' : 'file', file.id, value)
    ElMessage.success('重命名成功')
    emit('refresh:file-list', { folderId: 0 })
  } catch { /* cancelled */ }
}

async function deleteFile(file: FileEntry) {
  try { await ElMessageBox.confirm(`确定删除 "${file.file_name}"？`, '确认删除', { type: 'warning' }) } catch { return }
  try {
    await moveToRecycleBinRequest(file.is_folder ? 'folder' : 'file', file.id)
    ElMessage.success('已移至回收站')
    emit('refresh:file-list', { folderId: 0 })
  } catch { ElMessage.warning('删除失败') }
}

async function pasteToFolder(folderId: number | null) {
  if (!hasContent.value) return
  const items = currentClipboardItems.value
  const isCut = currentClipboardType.value === 'cut'
  for (const item of items) {
    try {
      if (isCut) {
        await moveEntryRequest(item.type, item.id, folderId)
      } else {
        await copyEntryRequest(item.type, item.id, folderId)
      }
    } catch { /* skip failed items */ }
  }
  if (isCut) clearClipboard()
  ElMessage.success(isCut ? '已移动' : '已粘贴')
  emit('refresh:file-list', { folderId: 0 })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

function handleSwitchWindow(id: string) {
  const w = windowManager.windows.find(x => x.id === id)
  if (w) {
    if (w.minimized || !w.isActive) { windowManager.activateWindow(id) } else { windowManager.toggleMinimized(id) }
  }
}
</script>
