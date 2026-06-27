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
import { restorePersistedIconPositions } from '@/desktop/drag-drop/drag-tool'
import {
  moveEntryRequest, emptyRecycleBinRequest,
} from '@/shared/api/desktop'
import type { FileEntry } from '@/shared/api/types'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'
import { useFileOperations } from '@/shared/files/use-file-operations'

const desktopIconGrid = defineAsyncComponent(() => import('@/desktop/shell/desktop-icon-grid.vue'))
const desktopWindowFrame = defineAsyncComponent(() => import('@/desktop/window-manager/desktop-window-frame.vue'))
const desktopTaskbar = defineAsyncComponent(() => import('@/desktop/taskbar/desktop-taskbar.vue'))
const desktopLauncher = defineAsyncComponent(() => import('@/desktop/launcher/desktop-launcher.vue'))
const desktopRightSidebar = defineAsyncComponent(() => import('@/desktop/shell/desktop-right-sidebar.vue'))
const windowManager = useWindowManager()
const { isEditorOrAbove: canBusinessWrite, currentRole } = usePermission()
const contextMenu = useContextMenu()
const userStore = useUserStore()
const { emit, on } = useDesktopEventBus()
const { isDragActive, onDragEnter, onDragLeave, onDrop } = useDesktopShellDropUpload()
const { desktopFileList, openDesktopEntry } = useDesktopRootFiles()
const { creatableFormats } = useCreatableFormats()
const { desktopAppList, launcherAppList, sidebarAppList, trayAppList, registryError, loading, desktopContainerRef, retryLoadRegistry, updateContainerSize } = useDesktopAppLoading(currentRole)
const { handleDesktopMouseDown } = useDesktopPointer()

const showLauncher = ref(false); const showRightSidebar = ref(false); const rightSidebarAppKey = ref('desktop')
const canWrite = computed(() => canBusinessWrite.value)

const wallpaper = 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0f172a"/><stop offset="50%" stop-color="#1d4ed8"/><stop offset="100%" stop-color="#7c3aed"/></linearGradient><radialGradient id="r" cx="30%" cy="20%" r="60%"><stop offset="0%" stop-color="rgba(191,219,254,0.35)"/><stop offset="100%" stop-color="rgba(15,23,42,0)"/></radialGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><rect width="100%" height="100%" fill="url(#r)"/></svg>')

function getSourceFolderId(key: string): number | null {
  const el = document.querySelector(`[data-selection-key="${key}"]`)
  if (!el) return null
  const fm = el.closest('.desktop-file-manager') as HTMLElement | null
  if (fm) {
    const attr = fm.getAttribute('data-folder')
    return attr !== null ? Number(attr) : 0
  }
  return 0
}

on('desktop:move-to-folder', async ({ ids, targetFolderId }) => {
  const targetId = targetFolderId !== null && targetFolderId !== undefined
    ? Number(targetFolderId)
    : null
  if (targetId !== null && !Number.isFinite(targetId)) return
  const affectedFolders = new Set<number>()
  affectedFolders.add(0)
  let movedCount = 0
  for (const id of ids) {
    const colonIdx = id.indexOf(':')
    if (colonIdx === -1) continue
    const type = id.slice(0, colonIdx) as 'file' | 'folder'
    const fileId = Number(id.slice(colonIdx + 1))
    if (!Number.isFinite(fileId)) continue
    if (fileId === targetId) continue
    const srcFolderId = getSourceFolderId(id)
    if (srcFolderId !== null && srcFolderId === targetId) continue
    try {
      await moveEntryRequest(type, fileId, targetId)
      movedCount += 1
      if (srcFolderId !== null) affectedFolders.add(srcFolderId)
    } catch (e: unknown) {
	      const err = e as { http_status?: number; response?: { status?: number } } | null
	      if (err?.http_status === 409 || err?.response?.status === 409) {
        ElMessage.warning('目标已有同名文件')
      }
    }
  }
  if (movedCount > 0) {
    ElMessage.success(movedCount > 1 ? `已移动 ${movedCount} 个项目` : '已移动')
    affectedFolders.forEach(folderId => {
      emit('refresh:file-list', { folderId })
    })
  }
})

function handleOpenApp(appKey: string) { windowManager.openWindow(appKey) }
function openSidebar(appKey = 'desktop') { rightSidebarAppKey.value = appKey; showRightSidebar.value = true }
function handleLauncherOpen(appKey: string) {
  showLauncher.value = false
  const app = getApp(appKey)
  if (app?.showInSidebar) openSidebar(appKey); else handleOpenApp(appKey)
}
async function handleLauncherCommand(command: string) {
  const { windows: ws, toggleMinimized: toggle } = windowManager
  if (command === 'refresh-desktop') updateContainerSize()
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
  requestAnimationFrame(() => restorePersistedIconPositions())
}

const fileOps = useFileOperations({ refresh: refreshDesktop })

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
  input.value = ''
  await fileOps.uploadFile(file, _pendingUploadFolderId)
}

// ── Menu Action Handlers ──────────────────────────────────────────────
async function handleContextMenuSelect(menuKey: string) {
  const menuContext = contextMenu.context.value
  contextMenu.close()
  const appKey = (menuContext?.target?.appKey as string) || ''
  const file = menuContext?.target as FileEntry | undefined

  // Global / Desktop actions
  if (menuKey === 'refresh-desktop' || menuKey === 'refresh') { refreshDesktop(); return }
  if (menuKey === 'open-desktop-file-manager') { windowManager.openWindow('desktop'); return }
  if (menuKey === 'open-recycle-bin') { windowManager.openWindow('recycle'); return }
  if (menuKey === 'open-app' && appKey) { windowManager.openWindow(appKey); return }

  // Desktop blank: upload, create folder, paste
  if (menuKey === 'upload-file') { triggerUpload(null); return }
  if (menuKey === 'new-folder' || menuKey === 'create-folder') { await fileOps.createFolder(null); return }
  if (menuKey === 'paste' && hasContent.value) {
    const isCut = currentClipboardType.value === 'cut'
    await fileOps.pasteToFolder(null, currentClipboardItems.value, isCut)
    if (isCut) clearClipboard()
    return
  }

  // File actions
  if (file && file.id) {
    if (menuKey === 'open') { openDesktopEntry(file); return }
    if (menuKey === 'download') { await fileOps.downloadFile(file); return }
    if (menuKey === 'copy-path') { await fileOps.copyPath(file); return }
    if (menuKey === 'details') { await showFileDetails(file); return }
    if (menuKey === 'rename' && canWrite.value) { await fileOps.renameEntry(file); return }
    if (menuKey === 'delete' && canWrite.value) { await fileOps.deleteEntry(file); return }
    if (menuKey === 'cut' && canWrite.value) { cutItems([{ id: file.id, type: file.is_folder ? 'folder' as const : 'file' as const, name: file.file_name }]); ElMessage.success('已剪切'); return }
    if (menuKey === 'copy' && canWrite.value) { copyItems([{ id: file.id, type: file.is_folder ? 'folder' as const : 'file' as const, name: file.file_name }]); ElMessage.success('已复制'); return }
  }

  // Folder-specific actions
  if (file && file.is_folder) {
    if (menuKey === 'upload-here' && canWrite.value) { triggerUpload(file.id); return }
    if (menuKey === 'create-folder-here' && canWrite.value) { await fileOps.createFolder(file.id); return }
    if (menuKey === 'paste-here' && canWrite.value && hasContent.value) {
      const isCut = currentClipboardType.value === 'cut'
      await fileOps.pasteToFolder(file.id, currentClipboardItems.value, isCut)
      if (isCut) clearClipboard()
      return
    }
  }

  // Create file by extension
  if (menuKey.startsWith('create-file:') && canWrite.value) {
    const ext = menuKey.slice('create-file:'.length)
    const folderId = (file && file.is_folder) ? file.id : null
    const format = creatableFormats.value.find(f => f.extension === ext)
    const label = format?.label || `.${ext} 文件`
    await fileOps.createFile(ext, folderId, label)
    return
  }

  // Recycle actions
  if (menuKey === 'empty-recycle-bin' && canWrite.value) {
    try { await ElMessageBox.confirm('确定清空回收站？', '确认', { type: 'warning' }) } catch { return }
    await emptyRecycleBinRequest(); ElMessage.success('回收站已清空'); emit('refresh:file-list', { folderId: 0 }); return
  }
}

// ── File Operations (delegated to shared useFileOperations) ────────────

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
