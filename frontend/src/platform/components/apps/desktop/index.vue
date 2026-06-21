<template>
  <div class="desktop-file-manager" @contextmenu.prevent="state.handleBlankContextMenu" @click="state.closeContextMenu">
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

    <div class="fm-body">
      <FmNavPane
        :current-folder-id="state.currentFolderId.value"
        :is-recycle-bin="state.isRecycleBin.value"
        @go-root="state.goRoot"
        @open-recycle="state.openRecycle"
      />

      <div class="fm-main">
        <FmRecycleView v-if="state.isRecycleBin.value" />
        <FmFileList
          v-else
          :items="state.sortedItems.value"
          :selected-id="state.selectedId.value"
          :view-mode="state.viewMode.value"
          :loading="state.loading.value"
          :display-name="state.displayName"
          :format-size="state.formatSize"
          :sort-column="state.sortColumn.value"
          :sort-direction="state.sortDirection.value"
          @select="state.selectItem"
          @open="state.openItem"
          @context-menu="state.handleItemMenu"
          @sort="handleSort"
          @drag-move="handleDragMove"
          @drag-move-to="handleDragMoveTo"
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

    <FmPropertiesDialog
      :visible="state.propertiesVisible.value"
      :item="state.propertiesItem.value"
      :display-name="state.displayName"
      :format-size="state.formatSize"
      @update:visible="state.closeProperties"
    />

    <input ref="uploadInputRef" type="file" class="fm-hidden-input" @change="state.onUploadFile" />

    <!-- Right-click menu -->
    <div v-if="state.ctxVisible.value" class="ctx-overlay" @click.self="state.closeContextMenu">
      <div class="ctx-menu" :style="{ left: state.ctxX.value + 'px', top: state.ctxY.value + 'px' }">
        <button
          v-for="item in state.ctxItems.value"
          :key="item.key"
          class="ctx-item"
          :class="{ 'ctx-danger': item.danger, 'ctx-disabled': item.disabled }"
          type="button"
          :disabled="item.disabled"
          @click="state.handleCtxClick(item.key)"
        >
          <span class="ctx-icon">{{ item.icon || '' }}</span>
          <span class="ctx-label">{{ item.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import FmNavigationBar from './file-manager/fm-navigation-bar.vue'
import FmNavPane from './file-manager/fm-nav-pane.vue'
import FmRecycleView from './file-manager/fm-recycle-view.vue'
import FmFileList from './file-manager/fm-file-list.vue'
import FmStatusBar from './file-manager/fm-status-bar.vue'
import FmPropertiesDialog from './file-manager/fm-properties-dialog.vue'
import { useFileManagerState } from './file-manager/use-file-manager-state'
import { moveEntryRequest } from '@/shared/api/desktop'
import type { FileEntry } from '@/shared/api/types'

const props = defineProps<{
  folderId?: number
  folderName?: string
}>()

const uploadInputRef = ref<HTMLInputElement | null>(null)
const state = useFileManagerState({
  folderId: () => props.folderId,
  folderName: () => props.folderName,
})

function handleSort(column: string) {
  if (state.sortColumn.value === column) {
    state.sortDirection.value = state.sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    state.sortColumn.value = column as 'name' | 'date' | 'type' | 'size'
    state.sortDirection.value = 'asc'
  }
}

async function handleDragMove(source: FileEntry, targetFolder: FileEntry) {
  if (!targetFolder.is_folder) return
  if (source.id === targetFolder.id) return
  try {
    await moveEntryRequest(source.is_folder ? 'folder' : 'file', source.id, targetFolder.id)
    await state.loadFiles()
  } catch {
    // 移动失败静默忽略
  }
}

async function handleDragMoveTo(source: FileEntry, targetFolderId: number | null) {
  // 移到当前位置则忽略
  const currentId = state.currentFolderId.value
  const tId = targetFolderId ?? 0
  if (tId === currentId) return
  try {
    await moveEntryRequest(source.is_folder ? 'folder' : 'file', source.id, targetFolderId ?? undefined)
    await state.loadFiles()
  } catch {
    // 移动失败静默忽略
  }
}

onMounted(() => {
  state.uploadInput.value = uploadInputRef.value
  state.applyInitialFolder()
  void state.loadFiles()
})
</script>

<style>
.nav-drop-over,
.nav-drop-over:hover {
  background: #dbeafe !important;
  border-color: #2395bc !important;
  box-shadow: 0 0 0 2px rgba(35, 149, 188, 0.2) !important;
}
</style>

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

.fm-hidden-input {
  display: none;
}

.ctx-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.ctx-menu {
  position: fixed;
  min-width: 150px;
  padding: 5px;
  border: 1px solid #d8dee8;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.16);
}

.ctx-item {
  width: 100%;
  height: 30px;
  border: none;
  border-radius: 5px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 9px;
  font-size: 13px;
  color: #263445;
  cursor: pointer;
  text-align: left;
}

.ctx-item:hover {
  background: #eaf4ff;
}

.ctx-disabled {
  color: #a8b1bf;
  cursor: not-allowed;
}

.ctx-danger {
  color: #dc2626;
}

.ctx-icon {
  width: 18px;
  text-align: center;
}

@media (max-width: 860px) {
  .fm-body {
    grid-template-columns: 170px minmax(0, 1fr);
  }
}

@media (max-width: 700px) {
  .fm-body {
    grid-template-columns: 1fr;
  }
  .fm-body > :first-child {
    display: none;
  }
}
</style>
