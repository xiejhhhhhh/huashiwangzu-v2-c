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
          :search-scope="state.searchScope.value"
          :view-mode="state.viewMode.value"
          :show-path-bar="showPathBar"
          :show-preview="showPreview"
          @go-back="state.goBack"
          @go-forward="state.goForward"
          @go-up="state.goUp"
          @go-root="state.goRoot"
          @navigate="state.navigateToCrumb"
          @update:search-keyword="state.setSearchKeyword($event)"
          @update:search-scope="setSearchScope"
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
          :active-tag="state.activeTagFilter.value"
          :documents-folder-id="state.locations.value.documents?.id ?? null"
          :downloads-folder-id="state.locations.value.downloads?.id ?? null"
          @go-root="() => { state.setTagFilter(null); state.goRoot() }"
          @open-recycle="() => { state.setTagFilter(null); state.openRecycle() }"
          @open-named="(key) => { state.setTagFilter(null); state.openNamedLocation(key) }"
          @filter-tag="state.setTagFilter"
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
        <div
          class="fm-body"
          @mousedown="onBodyMouseDown"
        >
          <FmFileList
            :items="state.sortedItems.value"
            :selected-id="state.selectedId.value"
            :selected-ids="state.selectedIds.value"
            :view-mode="state.viewMode.value"
            :icon-size="iconSize"
            :column-stack="state.columnStack.value"
            :column-widths="listColumnWidths"
            :loading="state.loading.value"
            :display-name="state.displayName"
            :format-size="state.formatSize"
            :sort-column="state.sortColumn.value"
            :sort-direction="state.sortDirection.value"
            :load-status="state.loadState.value.status"
            :load-error="state.loadState.value.error"
            :tags-of="state.tagsOf"
            :tag-revision="state.tagRevision.value"
            @select="onSelectItem"
            @open="handleItemOpen"
            @context-menu="handleItemContextMenu"
            @sort="handleSort"
            @update:column-widths="setListColumnWidths"
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
          <div
            v-if="marquee"
            class="fm-marquee"
            :style="marqueeStyle"
          />
        </div>
      </div>

      <template #statusbar>
        <FmStatusBar
          :item-count="state.items.value.length"
          :folder-count="state.folders.value.length"
          :file-count="state.files.value.length"
          :selected-item="state.selectedItem.value"
          :selected-size="selectedTotalSize || (state.selectedItem.value && !state.selectedItem.value.is_folder ? state.formatSize(state.selectedItem.value.file_size) : '')"
          :selected-count="state.selectedIds.value.length"
          :view-mode="state.viewMode.value"
          :search-keyword="state.searchKeyword.value"
          :search-scope="state.searchScope.value"
          :search-loading="state.searchLoading.value"
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

    <FmQuickLook
      :visible="state.quickLookVisible.value"
      :item="state.quickLookItem.value"
      :display-name="state.displayName"
      :format-size="state.formatSize"
      @close="state.closeQuickLook"
      @open="(item) => { state.closeQuickLook(); handleItemOpen(item) }"
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
import { ref, onMounted, watch, computed } from 'vue'
import { MacAppShell, useAppFeedback } from '@/desktop/app-kit'
import { dragState } from '@/desktop/drag-drop/drag-state'
import { useContextMenu } from '@/desktop/context-menu/use-context-menu'
import ContextMenu from '@/desktop/context-menu/context-menu.vue'
import { buildArrangeMenu, buildFileMenu, buildFolderMenu, buildMultiSelectMenu } from '@/desktop/context-menu/file-context-menu'
import { canUndo, undoLast } from './file-manager/finder-undo-stack'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'
import { hasContent } from '@/desktop/clipboard/clipboard-state'
import { restoreRecycleBinEntry, permanentlyDeleteEntry, emptyRecycleBinRequest } from '@/shared/api/desktop'
import { openAppById } from '@/desktop/app-registry/app-opener'
import { windowManager } from '@/desktop/window-manager/window-manager'
import FmNavigationBar from './file-manager/fm-navigation-bar.vue'
import FmNavPane from './file-manager/fm-nav-pane.vue'
import FmPathBar from './file-manager/fm-path-bar.vue'
import FmFileList from './file-manager/fm-file-list.vue'
import FmPreviewPane from './file-manager/fm-preview-pane.vue'
import FmQuickLook from './file-manager/fm-quick-look.vue'
import FmStatusBar from './file-manager/fm-status-bar.vue'
import FmPropertiesDialog from './file-manager/fm-properties-dialog.vue'
import { useFileManagerState } from './file-manager/use-file-manager-state'
import type { FinderFolderSort, FinderSortColumn } from './file-manager/fm-state'
import type { FileEntry } from '@/shared/api/types'
import type { MenuItemConfig } from '@/desktop/context-menu/use-context-menu'
import type { FinderTagColor } from './file-manager/finder-tags'
import emitter from '@/desktop/events'
import { readAppState, updateAppState } from '@/desktop/window-manager/desktop-state-store'

const props = defineProps<{
  folderId?: number
  folderName?: string
  windowId?: string
}>()

const feedback = useAppFeedback()
const uploadInputRef = ref<HTMLInputElement | null>(null)
const rootRef = ref<HTMLElement | null>(null)

type FinderListColumnWidths = {
  name?: number
  date?: number
  type?: number
  size?: number
}

type FinderGroupBy = 'none' | 'kind' | 'date'

type FinderUiPrefs = {
  iconSize?: number
  showPathBar?: boolean
  showPreview?: boolean
  viewMode?: string
  searchScope?: 'folder' | 'all'
  groupBy?: FinderGroupBy
  listColumnWidths?: FinderListColumnWidths
  folderViews?: Record<string, {
    sort?: FinderFolderSort
    listColumnWidths?: FinderListColumnWidths
  }>
}

const DEFAULT_LIST_COLUMN_WIDTHS: Required<FinderListColumnWidths> = {
  name: 220,
  date: 132,
  type: 88,
  size: 72,
}

function loadPrefs(): FinderUiPrefs {
  // multi-user: desktop appState is persisted in framework_desktop_states
  return readAppState<FinderUiPrefs>('files', 'finderUiPrefs', {})
}

function folderViewKey(folderId: number) {
  return String(folderId || 0)
}

function normalizeListColumnWidths(raw?: FinderListColumnWidths | null): Required<FinderListColumnWidths> {
  const clamp = (value: number | undefined, fallback: number, min: number, max: number) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return fallback
    return Math.min(max, Math.max(min, Math.round(value)))
  }
  return {
    name: clamp(raw?.name, DEFAULT_LIST_COLUMN_WIDTHS.name, 120, 560),
    date: clamp(raw?.date, DEFAULT_LIST_COLUMN_WIDTHS.date, 96, 240),
    type: clamp(raw?.type, DEFAULT_LIST_COLUMN_WIDTHS.type, 64, 180),
    size: clamp(raw?.size, DEFAULT_LIST_COLUMN_WIDTHS.size, 56, 140),
  }
}

const prefs = loadPrefs()
const iconSize = ref(typeof prefs?.iconSize === 'number' ? prefs.iconSize : 50)
const showPathBar = ref(prefs?.showPathBar !== false)
const showPreview = ref(prefs?.showPreview !== false)
const listColumnWidths = ref(normalizeListColumnWidths(prefs?.listColumnWidths))

function resolveFolderSort(folderId: number): FinderFolderSort | null {
  const current = loadPrefs()
  const sort = current.folderViews?.[folderViewKey(folderId)]?.sort
  if (!sort?.column) return null
  if (!['name', 'date', 'type', 'size'].includes(sort.column)) return null
  return {
    column: sort.column,
    direction: sort.direction === 'desc' ? 'desc' : 'asc',
  }
}

function resolveFolderColumnWidths(folderId: number): FinderListColumnWidths | null {
  const current = loadPrefs()
  const widths = current.folderViews?.[folderViewKey(folderId)]?.listColumnWidths
  return widths || null
}

function persistFolderSort(folderId: number, sort: FinderFolderSort) {
  const prev = loadPrefs()
  const key = folderViewKey(folderId)
  const folderViews = { ...(prev.folderViews || {}) }
  folderViews[key] = { ...(folderViews[key] || {}), sort }
  persistPrefs({ folderViews })
}

function persistFolderColumnWidths(folderId: number, widths: Required<FinderListColumnWidths>) {
  const prev = loadPrefs()
  const key = folderViewKey(folderId)
  const folderViews = { ...(prev.folderViews || {}) }
  folderViews[key] = { ...(folderViews[key] || {}), listColumnWidths: widths }
  // also keep global fallback
  persistPrefs({ folderViews, listColumnWidths: widths })
}

const state = useFileManagerState({
  folderId: () => props.folderId,
  folderName: () => props.folderName,
  windowId: () => props.windowId,
  resolveFolderSort,
  onFolderSortChange: persistFolderSort,
})
if (prefs?.viewMode && ['grid', 'list', 'column', 'gallery'].includes(prefs.viewMode)) {
  state.viewMode.value = prefs.viewMode as 'grid' | 'list' | 'column' | 'gallery'
}
if (prefs?.searchScope === 'all' || prefs?.searchScope === 'folder') {
  state.searchScope.value = prefs.searchScope
}
if (prefs?.groupBy === 'kind' || prefs?.groupBy === 'date' || prefs?.groupBy === 'none') {
  state.groupBy.value = prefs.groupBy
}
// apply remembered sort for the initial folder before first load
const initialFolderId = Number(props.folderId || 0)
const initialSort = resolveFolderSort(initialFolderId)
if (initialSort) {
  state.sortColumn.value = initialSort.column
  state.sortDirection.value = initialSort.direction
}
const initialCols = resolveFolderColumnWidths(initialFolderId)
if (initialCols) {
  listColumnWidths.value = normalizeListColumnWidths({
    ...listColumnWidths.value,
    ...initialCols,
  })
}

const selectedTotalSize = computed(() => {
  const items = state.selectedItems.value
  if (!items.length) return ''
  const total = items.reduce((sum, item) => sum + (item.is_folder ? 0 : (item.file_size || 0)), 0)
  if (!total) return items.length > 1 ? `${items.length} 项` : ''
  return state.formatSize(total)
})

const contextMenu = useContextMenu()
const { creatableFormats } = useCreatableFormats()

let ctxtFile: FileEntry | null = null

const marquee = ref<null | { x1: number; y1: number; x2: number; y2: number; originX: number; originY: number }>(null)
const marqueeStyle = computed(() => {
  const m = marquee.value
  if (!m) return {}
  const left = Math.min(m.x1, m.x2)
  const top = Math.min(m.y1, m.y2)
  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${Math.abs(m.x2 - m.x1)}px`,
    height: `${Math.abs(m.y2 - m.y1)}px`,
  }
})

function onSelectItem(item: FileEntry, opts?: { additive?: boolean; range?: boolean }) {
  state.selectItem(item, opts)
}

function onBodyMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  const target = e.target as HTMLElement
  if (target.closest('.fm-entry, .fm-column-row, .fm-gallery-thumb, .fm-preview-pane, button, input, a')) return
  if (state.viewMode.value === 'column') return
  const body = e.currentTarget as HTMLElement
  const rect = body.getBoundingClientRect()
  const x = e.clientX - rect.left + body.scrollLeft
  const y = e.clientY - rect.top + body.scrollTop
  marquee.value = { x1: x, y1: y, x2: x, y2: y, originX: e.clientX, originY: e.clientY }
  if (!(e.metaKey || e.ctrlKey || e.shiftKey)) state.clearSelection()

  const onMove = (ev: MouseEvent) => {
    if (!marquee.value) return
    marquee.value = {
      ...marquee.value,
      x2: ev.clientX - rect.left + body.scrollLeft,
      y2: ev.clientY - rect.top + body.scrollTop,
    }
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    const box = marquee.value
    marquee.value = null
    if (!box) return
    if (Math.abs(box.x2 - box.x1) < 4 && Math.abs(box.y2 - box.y1) < 4) return
    const left = Math.min(box.x1, box.x2)
    const right = Math.max(box.x1, box.x2)
    const top = Math.min(box.y1, box.y2)
    const bottom = Math.max(box.y1, box.y2)
    const hits: number[] = []
    body.querySelectorAll<HTMLElement>('[data-selection-key]').forEach((el) => {
      const er = el.getBoundingClientRect()
      const elLeft = er.left - rect.left + body.scrollLeft
      const elTop = er.top - rect.top + body.scrollTop
      const elRight = elLeft + er.width
      const elBottom = elTop + er.height
      const overlap = !(elRight < left || elLeft > right || elBottom < top || elTop > bottom)
      if (!overlap) return
      const key = el.getAttribute('data-selection-key') || ''
      const id = Number(key.split(':')[1])
      if (Number.isFinite(id)) hits.push(id)
    })
    if (hits.length) state.selectByIds(hits, hits[hits.length - 1])
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function persistPrefs(patch: Partial<FinderUiPrefs> = {}) {
  const prev = loadPrefs()
  updateAppState('files', 'finderUiPrefs', {
    ...prev,
    iconSize: iconSize.value,
    showPathBar: showPathBar.value,
    showPreview: showPreview.value,
    viewMode: state.viewMode.value,
    searchScope: state.searchScope.value,
    groupBy: state.groupBy.value,
    listColumnWidths: listColumnWidths.value,
    ...patch,
  })
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

function setSearchScope(scope: 'folder' | 'all') {
  state.setSearchScope(scope)
  persistPrefs({ searchScope: scope })
}

function setListColumnWidths(next: FinderListColumnWidths) {
  listColumnWidths.value = normalizeListColumnWidths({
    ...listColumnWidths.value,
    ...next,
  })
  persistFolderColumnWidths(state.currentFolderId.value || 0, listColumnWidths.value)
}

function setGroupBy(mode: FinderGroupBy) {
  state.setGroupBy(mode)
  persistPrefs({ groupBy: mode })
}

// when navigating folders, restore per-folder column widths if present
watch(() => state.currentFolderId.value, (folderId) => {
  const widths = resolveFolderColumnWidths(folderId || 0)
  if (widths) {
    listColumnWidths.value = normalizeListColumnWidths({
      ...DEFAULT_LIST_COLUMN_WIDTHS,
      ...widths,
    })
  }
})

function openFolderInNewWindow(item: FileEntry | null | undefined) {
  if (!item?.is_folder) return
  openAppById('desktop', {
    folderId: item.id,
    folderName: state.displayName(item),
  })
}

function commonTagsOf(items: FileEntry[]): FinderTagColor[] {
  if (!items.length) return []
  const sets = items.map((entry) => new Set(state.tagsOf(entry)))
  const first = [...sets[0]]
  return first.filter((tag) => sets.every((set) => set.has(tag))) as FinderTagColor[]
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

  const meta = e.metaKey || e.ctrlKey
  const key = e.key.toLowerCase()

  if (meta && (e.key === '[' || e.code === 'BracketLeft')) {
    e.preventDefault()
    if (state.canGoBack.value) state.goBack()
    return
  }
  if (meta && (e.key === ']' || e.code === 'BracketRight')) {
    e.preventDefault()
    if (state.canGoForward.value) state.goForward()
    return
  }
  if (meta && key === 'c') {
    if (state.selectedItems.value.length || state.selectedItem.value) {
      e.preventDefault()
      void state.handleAction('copy', state.selectedItem.value)
    }
    return
  }
  if (meta && key === 'x') {
    if (state.canWrite.value && (state.selectedItems.value.length || state.selectedItem.value)) {
      e.preventDefault()
      void state.handleAction('cut', state.selectedItem.value)
    }
    return
  }
  if (meta && key === 'v') {
    if (state.canWrite.value && hasContent.value) {
      e.preventDefault()
      void state.handleAction('paste', null)
    }
    return
  }
  if (meta && key === 'n') {
    e.preventDefault()
    openAppById('desktop', {
      folderId: state.currentFolderId.value || 0,
      folderName: state.breadcrumb.value[state.breadcrumb.value.length - 1]?.name || '桌面',
    })
    return
  }
  if (meta && key === 'd') {
    if (state.canWrite.value && (state.selectedItems.value.length || state.selectedItem.value)) {
      e.preventDefault()
      void state.handleAction('duplicate', state.selectedItem.value)
    }
    return
  }
  if (meta && key === 'i') {
    if (state.selectedItem.value) {
      e.preventDefault()
      void state.handleAction('details', state.selectedItem.value)
    }
    return
  }
  if (meta && key === 'f') {
    e.preventDefault()
    const input = rootRef.value?.querySelector('.fm-search-input') as HTMLInputElement | null
    input?.focus()
    input?.select()
    return
  }
  if (meta && key === 'o') {
    if (state.selectedItem.value) {
      e.preventDefault()
      handleItemOpen(state.selectedItem.value)
    }
    return
  }
  if (meta && key === 'w') {
    e.preventDefault()
    if (props.windowId) windowManager.closeWindow(props.windowId)
    return
  }
  if (meta && key === 'z' && !e.shiftKey) {
    e.preventDefault()
    void (async () => {
      if (!canUndo()) {
        feedback.info('没有可撤销的操作')
        return
      }
      const result = await undoLast()
      if (result.ok) {
        feedback.success(result.message)
        void state.loadFiles()
      } else {
        feedback.warning(result.message)
      }
    })()
    return
  }

  if (e.code === 'Space' || e.key === ' ') {
    e.preventDefault()
    if (state.quickLookVisible.value) state.closeQuickLook()
    else state.openQuickLook()
    return
  }
  if (state.quickLookVisible.value && e.key === 'Escape') {
    e.preventDefault()
    state.closeQuickLook()
    return
  }
  if (state.quickLookVisible.value && e.key === 'Enter') {
    e.preventDefault()
    const item = state.quickLookItem.value
    if (item) {
      state.closeQuickLook()
      handleItemOpen(item)
    }
    return
  }
  if (state.quickLookVisible.value && (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowLeft')) {
    const items = state.sortedItems.value
    if (!items.length) return
    e.preventDefault()
    const currentId = state.quickLookItem.value?.id ?? state.selectedId.value
    const idx = items.findIndex((item) => item.id === currentId)
    const nextIdx = (e.key === 'ArrowDown' || e.key === 'ArrowRight')
      ? Math.min(items.length - 1, Math.max(0, idx + 1))
      : Math.max(0, idx <= 0 ? 0 : idx - 1)
    const next = items[nextIdx]
    if (next) {
      state.selectItem(next)
      state.openQuickLook(next)
    }
    return
  }

  const items = state.sortedItems.value
  if (!items.length && !['Backspace', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return

  const idx = items.findIndex((item) => item.id === state.selectedId.value)

  if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
    e.preventDefault()
    const next = items[Math.min(items.length - 1, Math.max(0, idx + 1))] || items[0]
    if (next) state.selectItem(next, { range: e.shiftKey })
    return
  }
  if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
    e.preventDefault()
    if (idx <= 0) {
      const first = items[0]
      if (first) state.selectItem(first, { range: e.shiftKey })
      return
    }
    const prev = items[idx - 1]
    if (prev) state.selectItem(prev, { range: e.shiftKey })
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    if (state.selectedItem.value) handleItemOpen(state.selectedItem.value)
    return
  }
  if (e.key === 'Delete' || (meta && e.key === 'Backspace')) {
    if (state.selectedItems.value.length || state.selectedItem.value) {
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
  if (meta && key === 'a') {
    e.preventDefault()
    state.selectAll()
  }
}

function handleSort(column: string) {
  if (!['name', 'date', 'type', 'size'].includes(column)) return
  state.setSort(column as FinderSortColumn)
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
    {
      key: 'arrange',
      label: '整理方式',
      icon: '☰',
      children: buildArrangeMenu(state.groupBy.value),
    },
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
  // right-click on unselected item: switch selection to it
  if (!state.selectedIds.value.includes(item.id)) {
    state.selectItem(item)
  }
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

  const selected = state.selectedItems.value
  const multi = selected.length > 1 && selected.some((entry) => entry.id === item.id)
  const activeTags = multi ? commonTagsOf(selected) : state.tagsOf(item)
  let items: MenuItemConfig[]
  const sep = () => [{ key: `sep-${Date.now()}-${Math.random()}`, label: '', separator: true } as MenuItemConfig]
  if (multi) {
    items = buildMultiSelectMenu(state.canWrite.value, sep, selected.length, activeTags)
    contextMenu.open(e, items, { type: 'multi-select', target: { ...item } })
    return
  }
  if (item.is_folder) {
    items = buildFolderMenu(state.canWrite.value, sep, activeTags)
    if (state.canWrite.value && creatableFormats.value.length) {
      items.splice(4, 0, {
        key: 'new-file',
        label: '新建文件',
        icon: '📄',
        children: creatableFormats.value.map(f => ({ key: `create-file:${f.extension}`, label: f.label, icon: '' })),
      })
    }
  } else {
    items = buildFileMenu(state.canWrite.value, sep, activeTags)
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
  if (key === 'selection-info') return
  if (key === 'open-in-new-window') {
    openFolderInNewWindow(ctxtFile)
    return
  }
  if (key.startsWith('group-by:')) {
    const mode = key.slice('group-by:'.length) as FinderGroupBy
    if (mode === 'none' || mode === 'kind' || mode === 'date') setGroupBy(mode)
    return
  }
  const multiTargets = (ctxType === 'multi-select' || state.selectedItems.value.length > 1)
    ? state.selectedItems.value
    : null
  if (await state.applyTagAction(key, ctxtFile, multiTargets)) {
    const count = multiTargets?.length || 1
    if (key === 'tag:clear') feedback.success(count > 1 ? `已清除 ${count} 项标签` : '已清除标签')
    else if (key.startsWith('tag:')) feedback.success(count > 1 ? `已更新 ${count} 项标签` : '已更新标签')
    return
  }
  await state.handleAction(key, ctxtFile)
}

onMounted(async () => {
  state.uploadInput.value = uploadInputRef.value
  await Promise.all([
    state.ensureLocations(),
    state.loadTags(),
  ])
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
  --mac-app-surface: rgba(255, 255, 255, 0.92);
  --mac-app-surface-sidebar: color-mix(in srgb, var(--glass-panel-bg, rgba(246, 246, 250, 0.62)) 88%, transparent);
  --mac-app-surface-toolbar: color-mix(in srgb, var(--glass-menubar-bg, rgba(246, 246, 250, 0.28)) 70%, white);
  --mac-app-surface-status: color-mix(in srgb, var(--glass-panel-bg, rgba(246, 246, 250, 0.62)) 85%, white);
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
  position: relative;
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

.fm-marquee {
  position: absolute;
  z-index: 20;
  pointer-events: none;
  border: 1px solid color-mix(in srgb, var(--mac-app-accent, #0a84ff) 70%, white);
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 16%, transparent);
  border-radius: 3px;
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
  background: var(--mac-app-surface-sidebar);
  backdrop-filter: blur(22px) saturate(160%);
  -webkit-backdrop-filter: blur(22px) saturate(160%);
  overflow: visible;
}

:deep(.app-window-frame_statusbar) {
  background: var(--mac-app-surface-status);
  backdrop-filter: blur(16px) saturate(150%);
  -webkit-backdrop-filter: blur(16px) saturate(150%);
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
