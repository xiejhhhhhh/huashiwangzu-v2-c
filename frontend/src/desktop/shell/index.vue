<template>
  <div ref="desktopContainerRef" class="desktop-shell-container" @contextmenu.prevent="handleDesktopContextMenu" @mousedown="handleDesktopMouseDown" @dragover.prevent="onDragEnter" @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
    <div class="desktop-shell-wallpaper" :class="wallpaperClass" :style="wallpaperStyle" />
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
    <DesktopAppSwitcher ref="appSwitcherRef" :show="showAppSwitcher" :windows="windowManager.windows" @close="closeAppSwitcher" @activate="windowManager.activateWindow" />
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
     <DesktopToastHost />
     <DesktopDialogHost />
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, computed, nextTick, unref, watch, onMounted, onUnmounted } from 'vue'
import { desktopMessage, showAlert, showConfirm } from '@/desktop/feedback/desktop-feedback'
import DesktopToastHost from '@/desktop/feedback/desktop-toast-host.vue'
import DesktopDialogHost from '@/desktop/feedback/desktop-dialog-host.vue'
import { useDesktopConfig } from '@/desktop/config/desktop-preferences'
import { listDesktopSkins, type DesktopShellSkinId } from '@/desktop/skins'
import DesktopAppSwitcher from '@/desktop/launcher/desktop-app-switcher.vue'
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
  moveEntryRequest, copyEntryRequest, emptyRecycleBinRequest,
  resolveNameConflictRequest,
} from '@/shared/api/desktop'
import { ElMessageBox } from 'element-plus'
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
const showAppSwitcher = ref(false)
const appSwitcherRef = ref<{ move: (delta: number) => void; activateSelected: () => void } | null>(null)
let overlayReturnFocus: HTMLElement | null = null
const canWrite = computed(() => canBusinessWrite.value)
const activeWindow = computed(() => windowManager.windows.find(w => w.isActive && !w.minimized))
const activeMenuTitle = computed(() => activeWindow.value?.title || '桌面')
const desktopUserName = computed(() => userStore.userInfo?.display_name || userStore.userInfo?.displayName || userStore.userInfo?.username || '用户')
const menuClock = ref('')
let menuClockTimer: ReturnType<typeof window.setInterval> | undefined

const { applyCurrentShellSkin, setShellSkin, config: desktopShellConfig } = useDesktopConfig()

const DEFAULT_WALLPAPER_IMAGE = '/desktop/wallpaper-macos-default.svg'

const wallpaperStyle = computed(() => {
  const type = desktopShellConfig.wallpaperType || 'image'
  const value = desktopShellConfig.wallpaperValue || DEFAULT_WALLPAPER_IMAGE
  if (type === 'color') {
    return { backgroundImage: 'none', backgroundColor: value }
  }
  if (type === 'gradient') {
    return { backgroundImage: value, backgroundColor: 'transparent' }
  }
  // image (default): allow raw url or path
  const url = value.startsWith('url(') ? value : `url(${value})`
  return {
    backgroundImage: url,
    backgroundColor: 'transparent',
  }
})
const wallpaperClass = computed(() => `wallpaper-${desktopShellConfig.wallpaperType || 'image'}`)

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
  void nextTick(() => applyCurrentShellSkin(desktopContainerRef.value))
  updateMenuClock()
  menuClockTimer = window.setInterval(updateMenuClock, 30_000)
  window.addEventListener('keydown', handleGlobalShortcut, true)
  window.addEventListener('desktop:open-app-switcher', openAppSwitcher)
  window.addEventListener('desktop:close-app-switcher', closeAppSwitcher)
  window.__HSWZ_DESKTOP_SHELL__ = {
    openAppSwitcher,
    closeAppSwitcher,
    openSpotlight,
    openLaunchpad,
    getShellSkin: () => desktopShellConfig.shellSkin,
    setShellSkin: (skin: DesktopShellSkinId) => setShellSkin(skin, desktopContainerRef.value),
    listShellSkins: () => listDesktopSkins(),
  }
})

onUnmounted(() => {
  if (menuClockTimer !== undefined) window.clearInterval(menuClockTimer)
  window.removeEventListener('keydown', handleGlobalShortcut, true)
  window.removeEventListener('desktop:open-app-switcher', openAppSwitcher)
  window.removeEventListener('desktop:close-app-switcher', closeAppSwitcher)
})

function openLaunchpad() {
  if (showLauncher.value) {
    closeLaunchpad()
    return
  }
  rememberOverlayFocus()
  showSpotlight.value = false
  showAppSwitcher.value = false
  showLauncher.value = true
}

function openSpotlight() {
  rememberOverlayFocus()
  showLauncher.value = false
  showAppSwitcher.value = false
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

function openAppSwitcher() {
  rememberOverlayFocus()
  showSpotlight.value = false
  showLauncher.value = false
  showAppSwitcher.value = true
}
function closeAppSwitcher() {
  if (!showAppSwitcher.value) return
  showAppSwitcher.value = false
  restoreOverlayFocus()
}

function closeSystemOverlays() {
  const wasOpen = showLauncher.value || showSpotlight.value || showAppSwitcher.value
  showLauncher.value = false
  showSpotlight.value = false
  showAppSwitcher.value = false
  if (wasOpen) restoreOverlayFocus()
}

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  if (el.isContentEditable) return true
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || Boolean(el.closest('[contenteditable="true"]'))
}

/**
 * Web-safe shortcuts:
 * - Escape always closes overlays (does not steal browser keys).
 * - Optional desktop hotkeys are OFF by default (enableDesktopHotkeys).
 * - Never capture ⌘/Ctrl+W/T/N/R or system ⌘Space/⌘Tab by default.
 */
function handleGlobalShortcut(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (showLauncher.value || showSpotlight.value || showAppSwitcher.value) {
      event.preventDefault()
      closeSystemOverlays()
    }
    return
  }

  // While App Switcher is open, allow in-panel keys only (opened via UI/API).
  if (showAppSwitcher.value) {
    if (event.key === 'Enter') {
      event.preventDefault()
      appSwitcherRef.value?.activateSelected()
      return
    }
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault()
      appSwitcherRef.value?.move(event.key === 'ArrowRight' ? 1 : -1)
    }
    return
  }

  if (!desktopShellConfig.enableDesktopHotkeys) return
  if (isEditableTarget(event.target)) return

  const meta = event.metaKey || event.ctrlKey

  // Ctrl/⌘+Shift+Space → Spotlight (avoids OS/browser ⌘Space)
  if (meta && event.shiftKey && event.code === 'Space') {
    event.preventDefault()
    showAppSwitcher.value = false
    showSpotlight.value ? closeSpotlight() : openSpotlight()
    return
  }

  // Ctrl/⌘+Shift+` → App Switcher (never raw ⌘Tab)
  if (meta && event.shiftKey && (event.key === '`' || event.code === 'Backquote')) {
    event.preventDefault()
    if (!showAppSwitcher.value) openAppSwitcher()
    else appSwitcherRef.value?.move(1)
    return
  }

  // Ctrl/⌘+Shift+L → Launchpad
  if (meta && event.shiftKey && event.key.toLowerCase() === 'l') {
    event.preventDefault()
    openLaunchpad()
    return
  }

  // F11 or Ctrl/⌘+Shift+D → Show Desktop
  if (event.key === 'F11' || (meta && event.shiftKey && event.key.toLowerCase() === 'd')) {
    event.preventDefault()
    handleShowDesktop()
    return
  }

  // Ctrl/⌘+Shift+H → open Finder (desktop files app)
  if (meta && event.shiftKey && event.key.toLowerCase() === 'h') {
    event.preventDefault()
    handleOpenApp('desktop')
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

on('desktop:move-to-folder', async ({ ids, targetFolderId, copy }) => {
  let targetId = targetFolderId !== null && targetFolderId !== undefined
    ? Number(targetFolderId)
    : null
  if (targetId !== null && !Number.isFinite(targetId)) return
  // desktop root is virtual folder id 0 / null in API
  if (targetId === 0) targetId = null
  const isCopy = Boolean(copy)

  const affectedFolders = new Set<number>()
  affectedFolders.add(0)
  if (targetId !== null) affectedFolders.add(targetId)

  type MoveItem = { id: number; item_type: 'file' | 'folder' }
  const items: MoveItem[] = []
  for (const key of ids) {
    const colonIdx = key.indexOf(':')
    if (colonIdx === -1) continue
    const kind = key.slice(0, colonIdx)
    if (kind !== 'file' && kind !== 'folder') continue
    const fileId = Number(key.slice(colonIdx + 1))
    if (!Number.isFinite(fileId)) continue
    if (fileId === targetId) continue
    const srcFolderId = getSourceFolderId(key)
    // same-folder drop is no-op for move; copy still allowed (creates "xxx copy")
    if (!isCopy && srcFolderId !== null && srcFolderId === targetId) continue
    // desktop icons always use file:id even for folders — prefer list lookup when present
    let itemType: 'file' | 'folder' = kind === 'folder' ? 'folder' : 'file'
    if (kind === 'file') {
      const entry = desktopFileList.value?.find((f: FileEntry) => f.id === fileId)
      if (entry?.is_folder) itemType = 'folder'
    }
    items.push({ id: fileId, item_type: itemType })
    if (srcFolderId !== null) affectedFolders.add(srcFolderId)
  }
  if (!items.length) return

  async function resolveConflict(item: MoveItem, mode: 'move' | 'copy'): Promise<boolean> {
    try {
      await ElMessageBox.confirm(
        '目标已有同名项目。选择「替换」将把已有项目移入回收站；「保留两者」会自动重命名。',
        mode === 'move' ? '移动冲突' : '复制冲突',
        {
          distinguishCancelAndClose: true,
          confirmButtonText: '替换',
          cancelButtonText: '保留两者',
          type: 'warning',
        },
      )
      await resolveNameConflictRequest({
        action: 'replace',
        mode,
        item_type: item.item_type,
        item_id: item.id,
        target_folder_id: targetId,
      })
      return true
    } catch (action) {
      if (action === 'cancel') {
        await resolveNameConflictRequest({
          action: 'keep_both',
          mode,
          item_type: item.item_type,
          item_id: item.id,
          target_folder_id: targetId,
        })
        return true
      }
      return false
    }
  }

  let doneCount = 0
  // always process item-by-item so 409 can open conflict dialog
  for (const item of items) {
    try {
      if (isCopy) await copyEntryRequest(item.item_type, item.id, targetId)
      else await moveEntryRequest(item.item_type, item.id, targetId)
      doneCount += 1
    } catch (e: unknown) {
      const err = e as { http_status?: number; response?: { status?: number } } | null
      if (err?.http_status === 409 || err?.response?.status === 409) {
        const ok = await resolveConflict(item, isCopy ? 'copy' : 'move')
        if (ok) doneCount += 1
      }
    }
  }
  if (doneCount === 0 && items.length) {
    desktopMessage.warning(isCopy ? '复制失败' : '移动失败')
  }

  if (doneCount > 0) {
    if (doneCount === items.length) {
      desktopMessage.success(
        isCopy
          ? (doneCount > 1 ? `已复制 ${doneCount} 个项目` : '已复制')
          : (doneCount > 1 ? `已移动 ${doneCount} 个项目` : '已移动'),
      )
    } else if (isCopy) {
      desktopMessage.warning(`已复制 ${doneCount} 个，失败 ${items.length - doneCount} 个`)
    }
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
  else if (command === 'finder-go-documents') {
    handleOpenApp('desktop', { folderName: '文稿' })
    // payload folderId resolved by files app via locations on openNamedLocation if needed
  }
  else if (command === 'finder-go-downloads') {
    handleOpenApp('desktop', { folderName: '下载' })
  }
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

  // Desktop blank: view / sort (must not be silent no-ops)
  if (menuKey === 'view-auto-arrange') {
    desktopShellConfig.iconLayout = 'auto-arrange'
    desktopMessage.success('已开启自动排列')
    refreshDesktop()
    return
  }
  if (menuKey === 'view-free-arrange' || menuKey === 'view-medium-icons') {
    desktopShellConfig.iconLayout = 'free'
    desktopMessage.success('已切换为自由排列')
    return
  }
  if (menuKey === 'view-align-grid') {
    desktopShellConfig.iconLayout = 'auto-arrange'
    desktopMessage.success('已对齐到网格')
    refreshDesktop()
    return
  }
  if (menuKey === 'sort-name' || menuKey === 'sort-type' || menuKey === 'sort-date') {
    desktopShellConfig.iconLayout = 'auto-arrange'
    desktopShellConfig.iconSort = menuKey === 'sort-name' ? 'name' : menuKey === 'sort-type' ? 'type' : 'date'
    desktopMessage.success(
      menuKey === 'sort-name' ? '已按名称排列'
        : menuKey === 'sort-type' ? '已按类型排列'
          : '已按修改日期排列',
    )
    refreshDesktop()
    return
  }
  if (menuKey === 'toggle-icon-labels') {
    desktopShellConfig.showIconLabels = !desktopShellConfig.showIconLabels
    desktopMessage.success(desktopShellConfig.showIconLabels ? '已显示图标标签' : '已隐藏图标标签')
    return
  }
  if (menuKey === 'wallpaper-default') {
    desktopShellConfig.wallpaperType = 'image'
    desktopShellConfig.wallpaperValue = '/desktop/wallpaper-macos-default.svg'
    desktopMessage.success('已切换默认壁纸')
    return
  }
  if (menuKey === 'wallpaper-gradient-dusk') {
    desktopShellConfig.wallpaperType = 'gradient'
    desktopShellConfig.wallpaperValue = 'linear-gradient(145deg, #0f172a 0%, #7c3aed 48%, #f97316 100%)'
    desktopMessage.success('已切换暮色渐变')
    return
  }
  if (menuKey === 'wallpaper-gradient-ocean') {
    desktopShellConfig.wallpaperType = 'gradient'
    desktopShellConfig.wallpaperValue = 'linear-gradient(160deg, #0c4a6e 0%, #0284c7 42%, #67e8f9 100%)'
    desktopMessage.success('已切换海洋渐变')
    return
  }
  if (menuKey === 'wallpaper-solid-dark') {
    desktopShellConfig.wallpaperType = 'color'
    desktopShellConfig.wallpaperValue = '#0b1020'
    desktopMessage.success('已切换深空黑')
    return
  }

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
    if (menuKey === 'cut' && canWrite.value) {
      cutItems([{ id: file.id, type: file.is_folder ? 'folder' as const : 'file' as const, name: file.file_name, sourceFolderId: 0 }])
      desktopMessage.success('已剪切')
      return
    }
    if (menuKey === 'copy' && canWrite.value) {
      copyItems([{ id: file.id, type: file.is_folder ? 'folder' as const : 'file' as const, name: file.file_name, sourceFolderId: 0 }])
      desktopMessage.success('已复制')
      return
    }
    if (menuKey === 'duplicate' && canWrite.value) {
      await fileOps.pasteToFolder(0, [{ id: file.id, type: file.is_folder ? 'folder' : 'file', name: file.file_name }], false)
      return
    }
    if (menuKey === 'compress' && canWrite.value) {
      // reuse shared ops path via download-style compress not wired on shell; open finder
      desktopMessage.info('请在访达窗口中使用压缩')
      return
    }
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
    const ok = await showConfirm('确定清空回收站？', '确认', { tone: 'warning' })
    if (!ok) return
    await emptyRecycleBinRequest(); desktopMessage.success('回收站已清空'); emit('refresh:file-list', { folderId: 0 }); return
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
  await showAlert(lines.join('\n'), '属性')
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

function handleIconMoveToFolder(keys: string[], folderKey: string, copy = false) {
  // folderKey 格式为 "file:{id}"，提取 folderId；file:0 = 桌面根
  const colonIdx = folderKey.indexOf(':')
  if (colonIdx === -1) return
  const targetFolderId = folderKey.slice(colonIdx + 1)
  if (!Number.isFinite(Number(targetFolderId))) return
  emit('desktop:move-to-folder', { ids: keys, targetFolderId, copy })
}

function handleDropOnWindow(keys: string[], windowId: string, copy = false) {
  // 从窗口ID找到对应窗口的payload（获取目标文件夹ID）
  const w = windowManager.windows.find(x => x.id === windowId)
  if (!w) return
  const rawFolderId = w.payload?.folderId as number | string | null | undefined
  const targetFolderId = rawFolderId === null || rawFolderId === undefined ? null : String(rawFolderId)
  // 触发和拖到文件夹图标相同的事件
  emit('desktop:move-to-folder', { ids: keys, targetFolderId, copy })
}
</script>
