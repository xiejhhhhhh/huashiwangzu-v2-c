<template>
  <div
    class="desktop-file-manager"
    :data-folder="String(state.currentFolderId.value || 0)"
    data-mac-app-kit="mac-app-v1"
    data-mac-app-layout="finder"
    @contextmenu.prevent="handleBlankContextMenu"
  >
    <MacAppShell layout="finder" :sidebar-width="200">
      <template #toolbar>
        <FmNavigationBar
          :can-go-back="state.canGoBack.value"
          :can-go-forward="state.canGoForward.value"
          :can-go-up="state.canGoUp.value"
          :breadcrumb="state.breadcrumb.value"
          :search-keyword="state.searchKeyword.value"
          @go-back="state.goBack"
          @go-forward="state.goForward"
          @go-up="state.goUp"
          @go-root="state.goRoot"
          @navigate="state.navigateToCrumb"
          @update:search-keyword="state.searchKeyword.value = $event"
        />
      </template>

      <template #sidebar>
        <FmNavPane
          :current-folder-id="state.currentFolderId.value"
          :is-recycle-bin="state.isRecycleBin.value"
          @go-root="state.goRoot"
          @open-recycle="state.openRecycle"
        />
      </template>

      <div
        class="fm-main"
        :data-folder="String(state.currentFolderId.value || 0)"
        :class="{ 'fm-main-drag-over': dragState.dragOverId === String(state.currentFolderId.value) && dragState.isDragging }"
      >
        <FmFileList
          :items="state.sortedItems.value"
          :selected-id="state.selectedId.value"
          :view-mode="state.viewMode.value"
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
        />
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
          @update:view-mode="state.viewMode.value = $event"
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
import { ref, onMounted } from 'vue'
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
import FmFileList from './file-manager/fm-file-list.vue'
import FmStatusBar from './file-manager/fm-status-bar.vue'
import FmPropertiesDialog from './file-manager/fm-properties-dialog.vue'
import { useFileManagerState } from './file-manager/use-file-manager-state'
import type { FileEntry } from '@/shared/api/types'
import type { MenuItemConfig } from '@/desktop/context-menu/use-context-menu'
import emitter from '@/desktop/events'

const props = defineProps<{
  folderId?: number
  folderName?: string
}>()

const feedback = useAppFeedback()
const uploadInputRef = ref<HTMLInputElement | null>(null)
const state = useFileManagerState({
  folderId: () => props.folderId,
  folderName: () => props.folderName,
})
const contextMenu = useContextMenu()
const { creatableFormats } = useCreatableFormats()

let ctxtFile: FileEntry | null = null

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

onMounted(() => {
  state.uploadInput.value = uploadInputRef.value
  state.applyInitialFolder()
  void state.loadFiles()
})
</script>

<style scoped>
.desktop-file-manager {
  height: 100%;
  min-height: 0;
  position: relative;
  color: var(--mac-app-text, #1d1d1f);
}

.fm-main {
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
}

.fm-hidden-input {
  display: none;
}

.fm-main-drag-over {
  background: var(--mac-app-selection, rgba(0, 122, 255, 0.06)) !important;
  box-shadow: inset 0 0 0 1.5px var(--mac-app-accent, var(--desktop-accent, #007aff));
  border-radius: 8px;
}

:deep(.app-window-frame_toolbar) {
  padding: 0;
}

:deep(.app-window-frame_sidebar) {
  border-right: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
}

:deep(.app-window-frame--file-manager .app-window-frame_content) {
  padding: 0;
  background: var(--mac-app-surface, #fff);
}
</style>
