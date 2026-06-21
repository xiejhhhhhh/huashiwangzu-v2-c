<template>
  <div class="desktop-file-manager" data-folder="recycle" @contextmenu.prevent="handleBlankContextMenu">
    <FmNavigationBar
      :can-go-back="state.canGoBack.value"
      :can-go-forward="state.canGoForward.value"
      :can-go-up="state.canGoUp.value"
      :breadcrumb="state.breadcrumb.value"
      :search-keyword="state.searchKeyword.value"
      @go-back="state.goBack"
      @go-forward="state.goForward"
      @go-up="state.goUp"
      @go-root="handleGoRoot"
      @navigate="state.navigateToCrumb"
      @update:search-keyword="state.searchKeyword.value = $event"
    />

    <div class="fm-body">
      <FmNavPane
        :current-folder-id="state.currentFolderId.value"
        :is-recycle-bin="state.isRecycleBin.value"
        @go-root="handleGoRoot"
        @open-recycle="state.openRecycle"
      />

      <div class="fm-main">
        <FmFileList
          :items="state.sortedItems.value"
          :selected-id="state.selectedId.value"
          :view-mode="state.viewMode.value"
          :loading="state.loading.value"
          :display-name="state.displayName"
          :format-size="state.formatSize"
          :sort-column="state.sortColumn.value"
          :sort-direction="state.sortDirection.value"
          @select="state.selectItem"
          @open="handleItemOpen"
          @context-menu="handleItemContextMenu"
          @sort="handleSort"
        />
      </div>
    </div>

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
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useContextMenu } from '@/desktop/context-menu/use-context-menu'
import ContextMenu from '@/desktop/context-menu/context-menu.vue'
import { restoreRecycleBinEntry, permanentlyDeleteEntry, emptyRecycleBinRequest } from '@/shared/api/desktop'
import FmNavigationBar from '../desktop/file-manager/fm-navigation-bar.vue'
import FmNavPane from '../desktop/file-manager/fm-nav-pane.vue'
import FmFileList from '../desktop/file-manager/fm-file-list.vue'
import FmStatusBar from '../desktop/file-manager/fm-status-bar.vue'
import { useFileManagerState } from '../desktop/file-manager/use-file-manager-state'
import type { FileEntry } from '@/shared/api/types'
import type { MenuItemConfig } from '@/desktop/context-menu/use-context-menu'
import emitter from '@/desktop/events'

const state = useFileManagerState({
  folderId: () => undefined,
  folderName: () => undefined,
})
const contextMenu = useContextMenu()

let ctxtFile: FileEntry | null = null

function handleSort(column: string) {
  if (state.sortColumn.value === column) {
    state.sortDirection.value = state.sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    state.sortColumn.value = column as 'name' | 'date' | 'type' | 'size'
    state.sortDirection.value = 'asc'
  }
}

function handleGoRoot() {
  state.goRoot()
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
  }
}

function handleItemOpen(item: FileEntry) {
  if (state.isRecycleBin.value) {
    ElMessage.info('请先还原再打开文件')
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
  }
}

async function handleContextMenuSelect(key: string) {
  const ctxType = contextMenu.context.value?.type
  contextMenu.close()
  if (ctxType === 'recycle-bin' || ctxType === 'recycle-bin-item') {
    const item = ctxtFile
    if (key === 'restore' && item) {
      const itemType = item.is_folder ? 'folder' : 'file'
      try { await restoreRecycleBinEntry(itemType, item.id); ElMessage.success('已还原') }
      catch { ElMessage.warning('还原失败') }
    } else if (key === 'delete-permanently' && item) {
      const itemType = item.is_folder ? 'folder' : 'file'
      try { await ElMessageBox.confirm('确定彻底删除？', '确认', { type: 'warning' }) } catch { return }
      try { await permanentlyDeleteEntry(itemType, item.id); ElMessage.success('已删除') }
      catch { ElMessage.warning('删除失败') }
    } else if (key === 'empty-recycle-bin') {
      try { await ElMessageBox.confirm('确定清空回收站？', '确认', { type: 'warning' }) } catch { return }
      try { await emptyRecycleBinRequest(); ElMessage.success('已清空') }
      catch { ElMessage.warning('清空失败') }
    } else if (key === 'refresh') {
      void state.loadFiles()
    }
    emitter.emit('refresh:file-list', { folderId: 0 } as never)
  }
}

onMounted(() => {
  state.openRecycle()
})
</script>

<style scoped>
.desktop-file-manager {
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  background: #eef3f8;
  color: #1f2937;
}

.fm-body {
  min-height: 0;
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
}

.fm-main {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
}
</style>
