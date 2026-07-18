<template>
  <div
    ref="rootRef"
    class="desktop-file-manager"
    tabindex="0"
    :data-folder="String(state.currentFolderId.value || 0)"
    data-mac-app-kit="mac-app-v1"
    data-mac-app-layout="finder"
    @contextmenu.prevent="handleBlankContextMenu"
    @keydown="handleKeydown"
  >
    <MacAppShell layout="finder" :sidebar-width="216">
      <template #toolbar>
        <FmNavigationBar
          :can-go-back="state.canGoBack.value"
          :can-go-forward="state.canGoForward.value"
          :can-go-up="state.canGoUp.value"
          :breadcrumb="state.breadcrumb.value"
          :search-keyword="state.searchKeyword.value"
          :view-mode="state.viewMode.value"
          :show-path-bar="showPathBar"
          :show-preview="showPreview"
          @go-back="state.goBack"
          @go-forward="state.goForward"
          @go-up="state.goUp"
          @go-root="state.goRoot"
          @navigate="state.navigateToCrumb"
          @update:search-keyword="state.searchKeyword.value = $event"
          @update:view-mode="state.viewMode.value = $event"
          @update:show-path-bar="setShowPathBar"
          @update:show-preview="setShowPreview"
          @action="handleToolbarAction"
        />
      </template>

      <template #sidebar>
        <FmNavPane
          :current-folder-id="state.currentFolderId.value"
          :is-recycle-bin="state.isRecycleBin.value"
          :active-named="state.activeNamed.value"
          @go-root="state.goRoot"
          @open-recycle="state.openRecycle"
          @open-named="state.openNamedLocation"
        />
      </template>

      <div
        class="fm-main"
        :data-folder="String(state.currentFolderId.value || 0)"
        :class="{ 'fm-main-drag-over': dragState.dragOverId === String(state.currentFolderId.value) && dragState.isDragging }"
      >
        <FmPathBar
          v-if="showPathBar && !state.isRecycleBin.value"
          :crumbs="state.breadcrumb.value"
          @navigate="state.navigateToCrumb"
        />
        <div class="fm-body">
          <FmFileList
            :items="state.sortedItems.value"
            :selected-id="state.selectedId.value"
            :view-mode="state.viewMode.value"
            :icon-size="iconSize"
            :column-stack="state.columnStack.value"
            :loading="state.loading.value"
            :display-name="state.displayName"
            :format-size="state.formatSize"
            :sort-column="state.sortColumn.value"
            :sort-direction="state.sortDirection.value"
            :load-status="state.loadState.value.status"
            :load-error="state.loadState.value.error"
            @select="state.selectItem"
            @open="handleItemOpen"
            @context-menu="handleItemContextMenu"
            @sort="handleSort"
            @retry="state.loadFiles"
            @column-select="(item, col) => state.selectInColumn(item, col)"
            @column-open="(item, col) => state.selectInColumn(item, col)"
          />
          <FmPreviewPane
            v-if="showPreview && state.viewMode.value !== 'column' && state.viewMode.value !== 'gallery'"
            :item="state.selectedItem.value"
            :display-name="state.displayName"
            :format-size="state.formatSize"
          />
        </div>
      </div>

      <template #statusbar>
        <FmStatusBar
          :item-count="state.items.value.length"
          :folder-count="state.folders.value.length"
          :file-count="state.files.value.length"
          :selected-item="state.selectedItem.value"
          :selected-size="state.selectedItem.value ? state.formatSize(state.selectedItem.value.file_size) : ''"
          :view-mode="state.viewMode.value"
          :search-keyword="state.searchKeyword.value"
          :filtered-count="state.filteredItems.value.length"
          :display-name="state.displayName"
          :icon-size="iconSize"
          @update:view-mode="state.viewMode.value = $event"
          @update:icon-size="setIconSize"
        />
      </template>
    </MacAppShell>

    <FmPropertiesDialog
      :visible="state.propertiesVisible.value"
      :item="state.propertiesItem.value"
      :display-name="state.displayName"
      :format-size="state.formatSize"
      @update:visible="state.closeProperties"
    />

    <input ref="uploadInputRef" type="file" class="fm-hidden-input" @change="state.onUploadFile" />

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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { MacAppShell, useAppFeedback } from '@/desktop/app-kit'
import { dragState } from '@/desktop/drag-drop/drag-state'
import { useContextMenu } from '@/desktop/context-menu/use-context-menu'
import ContextMenu from '@/desktop/context-menu/context-menu.vue'
import { buildFileMenu, buildFolderMenu } from '@/desktop/context-menu/file-context-menu'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'
import { hasContent } from '@/desktop/clipboard/clipboard-state'
import { restoreRecycleBinEntry, permanentlyDeleteEntry, emptyRecycleBinRequest } from '@/shared/api/desktop'
import FmNavigationBar from './file-manager/fm-navigation-bar.vue'
import FmNavPane from './file-manager/fm-nav-pane.vue'
import FmPathBar from './file-manager/fm-path-bar.vue'
import FmFileList from './file-manager/fm-file-list.vue'
import FmPreviewPane from './file-manager/fm-preview-pane.vue'
import FmStatusBar from './file-manager/fm-status-bar.vue'
import FmPropertiesDialog from './file-manager/fm-properties-dialog.vue'
import { useFileManagerState } from './file-manager/use-file-manager-state'
import type { FileEntry } from '@/shared/api/types'
import type { MenuItemConfig } from '@/desktop/context-menu/use-context-menu'
import emitter from '@/desktop/events'

const props = defineProps<{
  folderId?: number
  folderName?: string
  windowId?: string
}>()

const feedback = useAppFeedback()
const uploadInputRef = ref<HTMLInputElement | null>(null)
const rootRef = ref<HTMLElement | null>(null)

const PREFS_KEY = 'finder.ui.prefs.v1'
function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (!raw) return null
    return JSON.parse(raw) as { iconSize?: number; showPathBar?: boolean; showPreview?: boolean; viewMode?: string }
  } catch {
    return null
  }
}
const prefs = loadPrefs()
const iconSize = ref(typeof prefs?.iconSize === 'number' ? prefs.iconSize : 50)
const showPathBar = ref(prefs?.showPathBar !== false)
const showPreview = ref(prefs?.showPreview !== false)

const state = useFileManagerState({
  folderId: () => props.folderId,
  folderName: () => props.folderName,
  windowId: () => props.windowId,
})
if (prefs?.viewMode && ['grid', 'list', 'column', 'gallery'].includes(prefs.viewMode)) {
  state.viewMode.value = prefs.viewMode as 'grid' | 'list' | 'column' | 'gallery'
}

const contextMenu = useContextMenu()
const { creatableFormats } = useCreatableFormats()

let ctxtFile: FileEntry | null = null

function persistPrefs() {
  localStorage.setItem(PREFS_KEY, JSON.stringify({
    iconSize: iconSize.value,
    showPathBar: showPathBar.value,
    showPreview: showPreview.value,
    viewMode: state.viewMode.value,
  }))
}

function setShowPathBar(v: boolean) {
  showPathBar.value = v
  persistPrefs()
}

function setShowPreview(v: boolean) {
  showPreview.value = v
  persistPrefs()
}

function setIconSize(v: number) {
  iconSize.value = v
  persistPrefs()
}

watch(() => state.viewMode.value, () => persistPrefs())

function handleToolbarAction(key: string) {
  if (key === 'upload-file') {
    void state.handleAction('upload-file', null)
    return
  }
  if (key === 'create-folder') {
    void state.handleAction('create-folder', null)
    return
  }
  if (key === 'refresh') {
    void state.loadFiles()
  }
}

function handleKeydown(e: KeyboardEvent) {
  const target = e.target as HTMLElement | null
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return

  const items = state.sortedItems.value
  if (!items.length && !['Backspace', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return

  const idx = items.findIndex((item) => item.id === state.selectedId.value)

  if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
    e.preventDefault()
    const next = items[Math.min(items.length - 1, Math.max(0, idx + 1))] || items[0]
    if (next) state.selectItem(next)
    return
  }
  if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
    e.preventDefault()
    if (idx <= 0) {
      const first = items[0]
      if (first) state.selectItem(first)
      return
    }
    const prev = items[idx - 1]
    if (prev) state.selectItem(prev)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    if (state.selectedItem.value) handleItemOpen(state.selectedItem.value)
    return
  }
  if (e.key === 'Delete' || ((e.metaKey || e.ctrlKey) && e.key === 'Backspace')) {
    if (state.selectedItem.value) {
      e.preventDefault()
      void state.handleAction('delete', state.selectedItem.value)
    }
    return
  }
  if (e.key === 'Backspace') {
    e.preventDefault()
    if (state.canGoUp.value) state.goUp()
    else state.goRoot()
    return
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a') {
    e.preventDefault()
    if (items[0]) state.selectItem(items[0])
  }
}

function handleSort(column: string) {
  if (state.sortColumn.value === column) {
    state.sortDirection.value = state.sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    state.sortColumn.value = column as 'name' | 'date' | 'type' | 'size'
    state.sortDirection.value = 'asc'
  }
}

function handleBlankContextMenu(e: MouseEvent) {
  ctxtFile = null
  const el = e.target as HTMLElement
  if (el.closest('.fm-entry') || el.closest('.fm-nav-pane')) return

  if (state.isRecycleBin.value) {
    const items: MenuItemConfig[] = [
      { key: 'refresh', label: '刷新', icon: '↻' },
    ]
    if (state.canWrite.value) {
      items.unshift({ key: 'empty-recycle-bin', label: '清空回收站', icon: '🧹', danger: true })
    }
    contextMenu.open(e, items, { type: 'recycle-bin' })
    return
  }

  const items: MenuItemConfig[] = [
    { key: 'upload-file', label: '上传文件', icon: '⬆', disabled: !state.canWrite.value },
    { key: 'create-folder', label: '新建文件夹', icon: '📁', disabled: !state.canWrite.value },
    { key: 'refresh', label: '刷新', icon: '↻' },
  ]
  if (state.canWrite.value && creatableFormats.value.length) {
    items.splice(2, 0, {
      key: 'new-file',
      label: '新建文件',
      icon: '📄',
      children: creatableFormats.value.map(f => ({ key: `create-file:${f.extension}`, label: f.label, icon: '' })),
    })
  }
  if (hasContent.value) {
    items.push({ key: 'paste', label: '粘贴', icon: '📌' })
  }
  contextMenu.open(e, items, { type: 'desktop-blank' })
}

function handleItemOpen(item: FileEntry) {
  if (state.isRecycleBin.value) {
    feedback.info('请先还原再打开文件')
    return
  }
  state.openItem(item)
}

function handleItemContextMenu(item: FileEntry, e: MouseEvent) {
  ctxtFile = item
  if (state.isRecycleBin.value) {
    const items: MenuItemConfig[] = []
    if (state.canWrite.value) {
      items.push(
        { key: 'restore', label: '还原', icon: '↩' },
        { key: 'delete-permanently', label: '彻底删除', icon: '🗑', danger: true },
      )
    }
    contextMenu.open(e, items, { type: 'recycle-bin-item' })
    return
  }

  let items: MenuItemConfig[]
  if (item.is_folder) {
    items = buildFolderMenu(state.canWrite.value, () => [])
    if (state.canWrite.value && creatableFormats.value.length) {
      items.splice(3, 0, {
        key: 'new-file',
        label: '新建文件',
        icon: '📄',
        children: creatableFormats.value.map(f => ({ key: `create-file:${f.extension}`, label: f.label, icon: '' })),
      })
    }
  } else {
    items = buildFileMenu(state.canWrite.value, () => [])
  }
  contextMenu.open(e, items, { type: item.is_folder ? 'folder' : 'file', target: { ...item } })
}

async function handleRecycleAction(key: string) {
  const item = ctxtFile
  if (key === 'restore' && item) {
    const itemType = item.is_folder ? 'folder' : 'file'
    try {
      await restoreRecycleBinEntry(itemType, item.id)
      feedback.success('已还原')
    } catch {
      feedback.warning('还原失败')
    }
  } else if (key === 'delete-permanently' && item) {
    const itemType = item.is_folder ? 'folder' : 'file'
    const ok = await feedback.confirm('确定彻底删除？', '确认', { tone: 'warning' })
    if (!ok) return
    try {
      await permanentlyDeleteEntry(itemType, item.id)
      feedback.success('已删除')
    } catch {
      feedback.warning('删除失败')
    }
  } else if (key === 'empty-recycle-bin') {
    const ok = await feedback.confirm('确定清空回收站？', '确认', { tone: 'warning' })
    if (!ok) return
    try {
      await emptyRecycleBinRequest()
      feedback.success('已清空')
    } catch {
      feedback.warning('清空失败')
    }
  } else if (key === 'refresh') {
    void state.loadFiles()
  }
  emitter.emit('refresh:file-list', { folderId: 0 } as never)
}

async function handleContextMenuSelect(key: string) {
  const ctxType = contextMenu.context.value?.type
  contextMenu.close()
  if (ctxType === 'recycle-bin' || ctxType === 'recycle-bin-item') {
    await handleRecycleAction(key)
    return
  }
  await state.handleAction(key, ctxtFile)
}

onMounted(async () => {
  state.uploadInput.value = uploadInputRef.value
  await state.ensureLocations()
  state.applyInitialFolder()
  void state.loadFiles()
  const name = state.breadcrumb.value[state.breadcrumb.value.length - 1]?.name || '桌面'
  state.syncWindowTitle(name)
  rootRef.value?.focus({ preventScroll: true })
})
</script>

<style scoped>
.desktop-file-manager {
  height: 100%;
  min-height: 0;
  position: relative;
  outline: none;
  color: var(--mac-app-text, #1d1d1f);
  --mac-app-toolbar-height: 44px;
  --mac-app-statusbar-height: 22px;
  --mac-app-surface: #ffffff;
  --mac-app-surface-sidebar: transparent;
  --mac-app-surface-toolbar: color-mix(in srgb, #f2f2f4 82%, white);
  --mac-app-surface-status: color-mix(in srgb, #f2f2f4 90%, white);
}

.fm-main {
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--mac-app-surface, #fff);
}

.fm-body {
  flex: 1;
  min-height: 0;
  display: flex;
  min-width: 0;
}

.fm-body > :deep(.fm-file-list) {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.fm-hidden-input {
  display: none;
}

.fm-main-drag-over {
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 8%, transparent) !important;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--mac-app-accent, #0a84ff) 45%, transparent);
  border-radius: 8px;
}

:deep(.mac-app-kit),
:deep(.app-window-frame) {
  height: 100%;
  min-height: 0;
  background: transparent;
}

:deep(.app-window-frame_toolbar) {
  padding: 0;
  min-height: 44px;
  background: var(--mac-app-surface-toolbar);
  border-bottom: 0;
  box-shadow: none;
}

:deep(.app-window-frame_sidebar) {
  border-right: 0;
  background: transparent;
  overflow: visible;
}

:deep(.app-window-frame_body) {
  background:
    linear-gradient(180deg, rgba(250, 250, 252, 0.92), rgba(255, 255, 255, 0.98));
}

:deep(.app-window-frame--file-manager .app-window-frame_content) {
  padding: 0;
  background: #fff;
  overflow: hidden;
}

:deep(.app-window-frame_statusbar) {
  min-height: 22px;
  background: var(--mac-app-surface-status);
  border-top: 0;
}
</style>
