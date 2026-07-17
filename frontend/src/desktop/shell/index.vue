<template>
  <div ref="desktopContainerRef" class="desktop-shell-container" @contextmenu.prevent="handleDesktopContextMenu" @mousedown="handleDesktopMouseDown" @dragover.prevent="onDragEnter" @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
    <div class="desktop-shell-wallpaper" :style="{ backgroundImage: `url(${wallpaper})` }" />
    <svg class="desktop-liquid-filter" width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
        <filter id="desktop-liquid-refraction" x="-6%" y="-6%" width="112%" height="112%">
          <feTurbulence type="fractalNoise" baseFrequency="0.012 0.018" numOctaves="2" seed="9" result="noise" />
          <feGaussianBlur in="noise" stdDeviation="2.2" result="softNoise" />
          <feDisplacementMap in="SourceGraphic" in2="softNoise" scale="10" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
    <MacMenuBar
      :active-title="activeMenuTitle"
      :active-window-id="activeWindow?.id"
      :username="desktopUserName"
      :clock="menuClock"
      :windows="windowManager.windows"
      @open-app="handleOpenApp"
      @open-spotlight="openSpotlight"
      @open-launchpad="openLaunchpad"
      @activate-window="windowManager.activateWindow"
      @minimize-window="windowManager.minimizeWindow"
      @zoom-window="windowManager.toggleMaximized"
      @close-window="windowManager.closeWindow"
      @show-desktop="handleShowDesktop"
      @command="handleLauncherCommand"
    />
    <div class="desktop-shell-icon-layer">
      <component :is="desktopIconGrid" :app-list="desktopAppList" :file-list="desktopFileList" @openApp="handleOpenApp" @openFile="openDesktopEntry" @app-context-menu="handleAppContextMenu" @file-context-menu="handleFileContextMenu" @move-to-folder="handleIconMoveToFolder" @drop-on-window="handleDropOnWindow" />
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
      :pre-maximize-state="w.preMaximizeState"
      :animation-origin="w.animationOrigin"
      @activate="windowManager.activateWindow"
      @close="windowManager.closeWindow"
      @minimize="windowManager.toggleMinimized"
      @maximize="windowManager.toggleMaximized"
      @update-position="windowManager.updateWindowPosition"
      @update-geometry="windowManager.updateWindowGeometry"
    />
    <component :is="desktopTaskbar" :items="unref(windowManager.taskbarItems)" :launcher-open="showLauncher" :app-list="allAppList" @switchWindow="handleSwitchWindow" @openLauncher="openLaunchpad" @openSpotlight="openSpotlight" @openApp="handleOpenApp" @closeWindow="windowManager.closeWindow" />
    <component :is="desktopLauncher" v-if="showLauncher" :show="showLauncher" :app-list="launcherAppList" @openApp="handleLauncherOpen" @execute-command="handleLauncherCommand" @close="closeLaunchpad" />
    <component :is="desktopSpotlight" v-if="showSpotlight" :show="showSpotlight" @close="closeSpotlight" />
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
      @dismiss="contextMenu.close"
    />
    <LoadStateBanner
      v-if="desktopFileLoadState.status === 'stale'"
      class="desktop-shell-file-stale"
      :status="desktopFileLoadState.status"
      :error="desktopFileLoadState.error"
      stale-text="桌面文件可能不是最新"
      @retry="loadDesktopFiles"
    />
    <div v-if="registryError" class="desktop-shell-error">
       <p>{{ registryError }}</p>
       <button @click="retryLoadRegistry">重试</button>
     </div>
     <div v-else-if="desktopFileLoadState.status === 'error'" class="desktop-shell-error">
       <p>{{ desktopFileLoadState.error?.userMessage || '桌面文件加载失败' }}</p>
       <button @click="loadDesktopFiles">重试</button>
     </div>
     <div v-if="isDragActive" class="desktop-shell-drop-hint">松开后上传到桌面</div>
     <!-- 首屏骨架屏 -->
     <div v-if="loading" class="desktop-skeleton-overlay">
       <div class="desktop-skeleton-menubar">
         <div class="skeleton-block" style="width:32px;height:32px;border-radius:8px;" />
         <div class="skeleton-block" style="width:120px;height:24px;" />
         <div style="flex:1" />
         <div class="skeleton-block" style="width:80px;height:20px;" />
         <div class="skeleton-block" style="width:20px;height:20px;border-radius:50%;" />
       </div>
       <div class="desktop-skeleton-icons">
         <div v-for="n in 8" :key="n" class="desktop-skeleton-icon-item">
           <div class="skeleton-block" style="width:48px;height:48px;border-radius:12px;" />
           <div class="skeleton-block" style="width:56px;height:12px;margin-top:8px;" />
         </div>
       </div>
       <div class="desktop-skeleton-dock">
         <div v-for="n in 6" :key="n" class="skeleton-block" style="width:40px;height:40px;border-radius:10px;" />
       </div>
     </div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, computed, nextTick, unref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useContextMenu } from '@/desktop/context-menu/use-context-menu'
import ContextMenu from '@/desktop/context-menu/context-menu.vue'
import { useWindowManager } from '@/desktop/window-manager/window-manager'
import { getApp } from '@/desktop/app-registry/app-registry'
import { openAppById } from '@/desktop/app-registry/app-opener'
import { usePermission } from '@/shared/composables/use-permission'
import { useUserStore } from '@/platform/stores/user'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import desktopEmitter from '@/desktop/events'

import SelectionBox from '@/desktop/selection/SelectionBox.vue'
import { useDesktopShellDropUpload } from './use-desktop-shell-drop-upload'
import { useDesktopRootFiles } from './use-desktop-root-files'
import { useDesktopAppLoading } from './use-desktop-app-loading'
import { useDesktopPointer } from './use-desktop-pointer'
import { useCommandRegistry } from './use-command-registry'
import { buildFileMenu, buildFolderMenu } from '@/desktop/context-menu/file-context-menu'
import { buildDesktopShellIconMenu as buildAppIconMenu, buildDesktopShellBlankMenu } from '@/desktop/context-menu/desktop-shell-context-menu'
import { buildRecycleBinMenu, buildRecycleBinItemMenu } from '@/desktop/context-menu/file-context-menu'
import { copyItems, cutItems, hasContent, currentClipboardType, currentClipboardItems, clearClipboard, getClipboardIdList } from '@/desktop/clipboard/clipboard-state'
import type { ClipboardItem } from '@/desktop/clipboard/clipboard-state'
// 旧 drag-tool 已被 icon-grid-model 替代，图标网格组件自管理位置
// import { restorePersistedIconPositions } from '@/desktop/drag-drop/drag-tool'
import {
  moveEntryRequest, emptyRecycleBinRequest,
} from '@/shared/api/desktop'
import type { FileEntry } from '@/shared/api/types'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'
import { useFileOperations } from '@/shared/files/use-file-operations'
import LoadStateBanner from '@/shared/components/load-state-banner.vue'
import MacMenuBar from '@/desktop/menubar/desktop-menu-bar.vue'

const desktopIconGrid = defineAsyncComponent(() => import('@/desktop/shell/desktop-icon-grid.vue'))
const desktopWindowFrame = defineAsyncComponent(() => import('@/desktop/window-manager/desktop-window-frame.vue'))
const desktopTaskbar = defineAsyncComponent(() => import('@/desktop/taskbar/desktop-taskbar.vue'))
const desktopLauncher = defineAsyncComponent(() => import('@/desktop/launcher/desktop-launcher.vue'))
const desktopSpotlight = defineAsyncComponent(() => import('@/desktop/launcher/desktop-spotlight.vue'))

// 暴露 event bus 到全局，供 agent 等模块触发桌面刷新
window.__DESKTOP_EVENT_BUS__ = desktopEmitter as Window['__DESKTOP_EVENT_BUS__']

const windowManager = useWindowManager()
const { isEditorOrAbove: canBusinessWrite, currentRole } = usePermission()
const contextMenu = useContextMenu()
const userStore = useUserStore()
const { emit, on } = useDesktopEventBus()
const { isDragActive, onDragEnter, onDragLeave, onDrop } = useDesktopShellDropUpload()
const { desktopFileList, desktopFileLoadState, loadDesktopFiles, openDesktopEntry } = useDesktopRootFiles()
const { creatableFormats } = useCreatableFormats()
const { allAppList, desktopAppList, launcherAppList, registryError, loading, desktopContainerRef, retryLoadRegistry, updateContainerSize } = useDesktopAppLoading(currentRole)
const { handleDesktopMouseDown } = useDesktopPointer()
const { registerAllApps, registerAllFiles } = useCommandRegistry(handleOpenApp, handleLauncherCommand, openDesktopEntry)

const showLauncher = ref(false)
const showSpotlight = ref(false)
let overlayReturnFocus: HTMLElement | null = null
const canWrite = computed(() => canBusinessWrite.value)
const activeWindow = computed(() => windowManager.windows.find(w => w.isActive && !w.minimized))
const activeMenuTitle = computed(() => activeWindow.value?.title || '桌面')
const desktopUserName = computed(() => userStore.userInfo?.display_name || userStore.userInfo?.displayName || userStore.userInfo?.username || '用户')
const menuClock = ref('')
let menuClockTimer: ReturnType<typeof window.setInterval> | undefined

const wallpaper = 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000"><defs><linearGradient id="sky" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#082f49"/><stop offset=".42" stop-color="#0f766e"/><stop offset=".72" stop-color="#2563eb"/><stop offset="1" stop-color="#312e81"/></linearGradient><radialGradient id="sun" cx=".18" cy=".22" r=".42"><stop offset="0" stop-color="#fde68a" stop-opacity=".9"/><stop offset=".44" stop-color="#fb923c" stop-opacity=".28"/><stop offset="1" stop-color="#fb923c" stop-opacity="0"/></radialGradient><radialGradient id="water" cx=".72" cy=".62" r=".58"><stop offset="0" stop-color="#67e8f9" stop-opacity=".62"/><stop offset=".54" stop-color="#0ea5e9" stop-opacity=".24"/><stop offset="1" stop-color="#020617" stop-opacity="0"/></radialGradient><filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="8"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 .07"/></feComponentTransfer></filter></defs><rect width="1600" height="1000" fill="url(#sky)"/><rect width="1600" height="1000" fill="url(#sun)"/><rect width="1600" height="1000" fill="url(#water)"/><path d="M0 710 C260 560 440 820 710 640 C980 460 1200 660 1600 520 L1600 1000 L0 1000 Z" fill="#031525" opacity=".38"/><path d="M0 780 C310 700 510 920 780 760 C1050 600 1320 760 1600 620 L1600 1000 L0 1000 Z" fill="#e0f2fe" opacity=".12"/><rect width="1600" height="1000" filter="url(#grain)"/></svg>')

function updateMenuClock() {
  const now = new Date()
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const hour = String(now.getHours()).padStart(2, '0')
  const minute = String(now.getMinutes()).padStart(2, '0')
  menuClock.value = `${now.getMonth() + 1}月${now.getDate()}日 ${weekdays[now.getDay()]} ${hour}:${minute}`
}

watch(allAppList, apps => registerAllApps(apps), { immediate: true })
watch(desktopFileList, files => registerAllFiles(files), { immediate: true })

onMounted(() => {
  updateMenuClock()
  menuClockTimer = window.setInterval(updateMenuClock, 30_000)
  window.addEventListener('keydown', handleGlobalShortcut)
})

onUnmounted(() => {
  if (menuClockTimer !== undefined) window.clearInterval(menuClockTimer)
  window.removeEventListener('keydown', handleGlobalShortcut)
})

function openLaunchpad() {
  if (showLauncher.value) {
    closeLaunchpad()
    return
  }
  rememberOverlayFocus()
  showSpotlight.value = false
  showLauncher.value = true
}

function openSpotlight() {
  rememberOverlayFocus()
  showLauncher.value = false
  showSpotlight.value = true
}

function rememberOverlayFocus() {
  if (showLauncher.value || showSpotlight.value) return
  const active = document.activeElement
  overlayReturnFocus = active instanceof HTMLElement && active !== document.body ? active : null
}

function restoreOverlayFocus() {
  const target = overlayReturnFocus
  overlayReturnFocus = null
  if (target?.isConnected) nextTick(() => target.focus())
}

function closeLaunchpad() {
  if (!showLauncher.value) return
  showLauncher.value = false
  restoreOverlayFocus()
}

function closeSpotlight() {
  if (!showSpotlight.value) return
  showSpotlight.value = false
  restoreOverlayFocus()
}

function closeSystemOverlays() {
  const wasOpen = showLauncher.value || showSpotlight.value
  showLauncher.value = false
  showSpotlight.value = false
  if (wasOpen) restoreOverlayFocus()
}

function handleGlobalShortcut(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.code === 'Space') {
    event.preventDefault()
    showSpotlight.value ? closeSpotlight() : openSpotlight()
    return
  }
  if (event.key === 'Escape') {
    closeSystemOverlays()
  }
}

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
    const fileId = Number(id.slice(colonIdx + 1))
    if (!Number.isFinite(fileId)) continue
    if (fileId === targetId) continue
    // 通过 desktopFileList 查找该项判断是文件还是文件夹
    const entry = desktopFileList.value?.find((f: FileEntry) => f.id === fileId)
    const type: 'file' | 'folder' = entry?.is_folder ? 'folder' : 'file'
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

function handleOpenApp(appKey: string, payload?: Record<string, unknown>): string | null {
  return openAppById(appKey, payload)
}
function handleLauncherOpen(appKey: string) {
  closeLaunchpad()
  handleOpenApp(appKey)
}
async function handleLauncherCommand(command: string) {
  if (command === 'refresh-desktop') refreshDesktop()
  else if (command === 'logout') { await userStore.logout(); window.location.href = '/' }
  else if (command === 'open-profile') handleOpenApp('user-profile')
  else if (command === 'new-folder' && canWrite.value) await fileOps.createFolder(null)
  else if (command === 'minimize-all') windowManager.showDesktop()
  else if (command === 'restore-all') windowManager.restoreDesktop()
  closeSystemOverlays()
}

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
  if (menuKey === 'open-desktop-file-manager') { handleOpenApp('desktop'); return }
  if (menuKey === 'open-recycle-bin') { handleOpenApp('recycle'); return }
  if (menuKey === 'open-app' && appKey) { handleOpenApp(appKey); return }

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
  if (w) windowManager.activateWindow(id)
}
function handleShowDesktop() {
  windowManager.toggleDesktopVisibility()
}

function handleIconMoveToFolder(keys: string[], folderKey: string) {
  // folderKey 格式为 "file:{id}"，提取 folderId
  const colonIdx = folderKey.indexOf(':')
  if (colonIdx === -1) return
  const targetFolderId = folderKey.slice(colonIdx + 1)
  if (!Number.isFinite(Number(targetFolderId))) return
  emit('desktop:move-to-folder', { ids: keys, targetFolderId })
}

function handleDropOnWindow(keys: string[], windowId: string) {
  // 从窗口ID找到对应窗口的payload（获取目标文件夹ID）
  const w = windowManager.windows.find(x => x.id === windowId)
  if (!w) return
  const rawFolderId = w.payload?.folderId as number | string | null | undefined
  const targetFolderId = rawFolderId === null || rawFolderId === undefined ? null : String(rawFolderId)
  // 触发和拖到文件夹图标相同的事件
  emit('desktop:move-to-folder', { ids: keys, targetFolderId })
}
</script>
