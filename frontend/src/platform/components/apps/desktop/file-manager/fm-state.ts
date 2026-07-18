import { computed, ref, watch } from 'vue'
import { fetchFileList, fetchFinderLocations, fetchRecycleBinList, searchFilesRequest } from '@/shared/api/desktop'
import type { FinderLocation } from '@/shared/api/desktop'
import type { RecycleBinEntry } from '@/shared/api/types'
import { openFileByRecord } from '@/desktop/app-registry/app-opener'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import type { FileEntry } from '@/shared/api/types'
import { formatFileDisplayName } from '@/shared/files/display-name'
import type { DesktopFileManagerBreadcrumbItem, NavigationEntry } from './types'
import { createLoadState, failLoading, finishLoading, startLoading } from '@/shared/composables/use-load-state'
import { windowManager } from '@/desktop/window-manager/window-manager'
import {
  FINDER_TAGS,
  clearItemTags,
  getItemTags,
  toggleItemTag,
  type FinderTagColor,
} from './finder-tags'

export type FinderSortColumn = 'name' | 'date' | 'type' | 'size'
export type FinderSortDirection = 'asc' | 'desc'
export type FinderFolderSort = { column: FinderSortColumn; direction: FinderSortDirection }

interface CreateFileManagerStateOptions {
  folderId: () => number | undefined
  folderName: () => string | undefined
  windowId?: () => string | undefined
  /** per-folder sort memory; root uses folderId 0 */
  resolveFolderSort?: (folderId: number) => FinderFolderSort | null | undefined
  onFolderSortChange?: (folderId: number, sort: FinderFolderSort) => void
}

export function createFileManagerState(options: CreateFileManagerStateOptions) {
  const { emit, on } = useDesktopEventBus()

  const currentFolderId = ref<number>(0)
  const items = ref<FileEntry[]>([])
  const loadState = createLoadState<FileEntry[]>([])
  const loading = ref(false)
  const uploadInput = ref<HTMLInputElement | null>(null)
  const breadcrumb = ref<DesktopFileManagerBreadcrumbItem[]>([{ id: null, name: '桌面' }])
  const viewMode = ref<'grid' | 'list' | 'column' | 'gallery'>('grid')
  const activeNamed = ref<'documents' | 'downloads' | null>(null)
  const locations = ref<Record<string, FinderLocation>>({
    desktop: { key: 'desktop', id: 0, name: '桌面' },
  })
  const selectedId = ref<number | null>(null)
  const selectedIds = ref<number[]>([])
  const selectionAnchorId = ref<number | null>(null)
  const quickLookVisible = ref(false)
  const quickLookItem = ref<FileEntry | null>(null)
  /** local tag map revision — bump to refresh list/sidebar dots */
  const tagRevision = ref(0)
  const activeTagFilter = ref<FinderTagColor | null>(null)
  /** Miller Columns: stack of folder columns (folderId + items + selection) */
  const columnStack = ref<Array<{ folderId: number; name: string; items: FileEntry[]; selectedId: number | null }>>([])

  const sortColumn = ref<'name' | 'date' | 'type' | 'size'>('name')
  const sortDirection = ref<'asc' | 'desc'>('asc')
  const searchKeyword = ref('')
  const searchScope = ref<'folder' | 'all'>('folder')
  const searchResults = ref<FileEntry[] | null>(null)
  const searchLoading = ref(false)
  let searchTimer: ReturnType<typeof setTimeout> | null = null
  let searchToken = 0
  const navigationHistory = ref<NavigationEntry[]>([{ id: 0, name: '桌面' }])
  const navigationBreadcrumbs = ref<DesktopFileManagerBreadcrumbItem[][]>([[{ id: null, name: '桌面' }]])
  const historyIndex = ref(0)

  const isRecycleBin = ref(false)
  const propertiesVisible = ref(false)
  const propertiesItem = ref<FileEntry | null>(null)

  const folders = computed(() => items.value.filter(item => item.is_folder))
  const files = computed(() => items.value.filter(item => !item.is_folder))

  function itemTypeOf(item: FileEntry): 'file' | 'folder' {
    return item.is_folder ? 'folder' : 'file'
  }

  function tagsOf(item: FileEntry): FinderTagColor[] {
    void tagRevision.value
    return getItemTags(itemTypeOf(item), item.id)
  }

  const filteredItems = computed(() => {
    const keyword = searchKeyword.value.trim()
    let filtered = items.value
    // both scopes use server search results when available
    if (keyword && searchResults.value) {
      filtered = searchResults.value
    } else if (keyword) {
      const needle = keyword.toLowerCase()
      filtered = filtered.filter(item => item.file_name.toLowerCase().includes(needle))
    }
    if (activeTagFilter.value) {
      const tag = activeTagFilter.value
      filtered = filtered.filter((item) => tagsOf(item).includes(tag))
    }
    const folderList = filtered.filter(item => item.is_folder)
    const fileList = filtered.filter(item => !item.is_folder)
    const dir = sortDirection.value === 'asc' ? 1 : -1
    function sortByColumn(list: FileEntry[]): FileEntry[] {
      return [...list].sort((a, b) => {
        let cmp = 0
        switch (sortColumn.value) {
          case 'name': cmp = a.file_name.localeCompare(b.file_name); break
          case 'date': {
            const da = a.updated_at || a.created_at || ''
            const db = b.updated_at || b.created_at || ''
            cmp = da.localeCompare(db)
            break
          }
          case 'type': cmp = (a.format || '').localeCompare(b.format || ''); break
          case 'size': cmp = a.file_size - b.file_size; break
        }
        return cmp * dir
      })
    }
    return [...sortByColumn(folderList), ...sortByColumn(fileList)]
  })
  const sortedItems = filteredItems

  const selectedItem = computed(() => {
    if (selectedId.value != null) {
      return items.value.find(item => item.id === selectedId.value)
        || sortedItems.value.find(item => item.id === selectedId.value)
        || null
    }
    if (selectedIds.value.length) {
      return sortedItems.value.find(item => item.id === selectedIds.value[selectedIds.value.length - 1]) || null
    }
    return null
  })
  const selectedItems = computed(() => {
    const set = new Set(selectedIds.value)
    return sortedItems.value.filter(item => set.has(item.id))
  })
  const canGoUp = computed(() => !isRecycleBin.value && breadcrumb.value.length > 1)
  const pageTitle = computed(() => breadcrumb.value.map(item => item.name).join(' / '))
  const selectedSummary = computed(() => selectedItem.value ? `当前选中 ${displayName(selectedItem.value)}` : '系统文件管理器')

  const canGoBack = computed(() => !isRecycleBin.value && historyIndex.value > 0)
  const canGoForward = computed(() => !isRecycleBin.value && historyIndex.value < navigationHistory.value.length - 1)

  // 仅外部打开（桌面双击文件夹开窗）时按 props 初始化。
  // 内部导航会 push breadcrumb，不能被 payload 回写截成两级。
  watch(options.folderId, (raw) => {
    const next = Number(raw || 0)
    if (!Number.isFinite(next)) return
    if (next === currentFolderId.value) return
    applyInitialFolder()
    enterFolder(currentFolderId.value)
  })

  watch(options.folderName, (name) => {
    const label = typeof name === 'string' ? name.trim() : ''
    if (!label) return
    const last = breadcrumb.value[breadcrumb.value.length - 1]
    if (last && (last.id === currentFolderId.value || (currentFolderId.value === 0 && last.id == null))) {
      last.name = label
    }
  })

  on('refresh:file-list', (data: { folderId?: number }) => {
    if (data.folderId === undefined || data.folderId === null || data.folderId === 0 || data.folderId === currentFolderId.value) {
      void loadFiles()
    }
  })

  function applyInitialFolder() {
    const folderId = Number(options.folderId() || 0)
    currentFolderId.value = Number.isFinite(folderId) ? folderId : 0
    breadcrumb.value = currentFolderId.value
      ? [{ id: null, name: '桌面' }, { id: currentFolderId.value, name: options.folderName() || '文件夹' }]
      : [{ id: null, name: '桌面' }]
    clearSelection()
    navigationHistory.value = currentFolderId.value
      ? [{ id: 0, name: '桌面' }, { id: currentFolderId.value, name: options.folderName() || '文件夹' }]
      : [{ id: 0, name: '桌面' }]
    navigationBreadcrumbs.value = currentFolderId.value
      ? [[{ id: null, name: '桌面' }], [{ id: null, name: '桌面' }, { id: currentFolderId.value, name: options.folderName() || '文件夹' }]]
      : [[{ id: null, name: '桌面' }]]
    historyIndex.value = navigationHistory.value.length - 1
  }

  function mapRecycleToFileEntry(item: RecycleBinEntry): FileEntry {
    return {
      id: item.id,
      file_name: item.name,
      is_folder: item.item_type === 'folder',
      format: item.format ?? null,
      created_at: item.deleted_at,
      file_size: item.size ?? 0,
      storage_path: null,
    }
  }

  async function loadFiles() {
    loading.value = true
    startLoading(loadState)
    try {
      let nextItems: FileEntry[]
      if (isRecycleBin.value) {
        const data = await fetchRecycleBinList()
        nextItems = (data || []).map(mapRecycleToFileEntry)
      } else {
        const data = await fetchFileList(currentFolderId.value)
        nextItems = data?.items || []
      }
      items.value = nextItems
      finishLoading(loadState, nextItems)
      if (searchKeyword.value.trim() && !isRecycleBin.value) {
        void runSearch(searchKeyword.value)
      }
    } catch (error: unknown) {
      failLoading(loadState, error, '文件列表加载失败')
    } finally {
      loading.value = false
    }
  }

  function clearSearchResults() {
    searchResults.value = null
    searchLoading.value = false
  }

  async function runSearch(raw: string) {
    const keyword = raw.trim()
    if (!keyword || isRecycleBin.value) {
      clearSearchResults()
      return
    }
    const token = ++searchToken
    searchLoading.value = true
    try {
      // folder scope: recursive under current folder (Finder-like); all = global
      const page = searchScope.value === 'folder'
        ? await searchFilesRequest(keyword, undefined, 1, 200, {
            folderId: currentFolderId.value || 0,
            recursive: true,
          })
        : await searchFilesRequest(keyword, undefined, 1, 200)
      if (token !== searchToken) return
      searchResults.value = page.items || []
    } catch {
      if (token !== searchToken) return
      searchResults.value = []
    } finally {
      if (token === searchToken) searchLoading.value = false
    }
  }

  function scheduleSearch() {
    if (searchTimer) clearTimeout(searchTimer)
    const keyword = searchKeyword.value.trim()
    if (!keyword || isRecycleBin.value) {
      clearSearchResults()
      return
    }
    searchTimer = setTimeout(() => {
      void runSearch(keyword)
    }, 220)
  }

  function setSearchScope(scope: 'folder' | 'all') {
    if (searchScope.value === scope) return
    searchScope.value = scope
    if (searchKeyword.value.trim()) scheduleSearch()
    else clearSearchResults()
  }

  function setSearchKeyword(value: string) {
    searchKeyword.value = value
    if (value.trim()) scheduleSearch()
    else clearSearchResults()
  }

  function applyFolderSort(folderId: number) {
    const remembered = options.resolveFolderSort?.(folderId)
    if (remembered?.column) {
      sortColumn.value = remembered.column
      sortDirection.value = remembered.direction === 'desc' ? 'desc' : 'asc'
      return
    }
    sortColumn.value = 'name'
    sortDirection.value = 'asc'
  }

  function setSort(column: FinderSortColumn, direction?: FinderSortDirection) {
    if (direction) {
      sortColumn.value = column
      sortDirection.value = direction
    } else if (sortColumn.value === column) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortColumn.value = column
      sortDirection.value = 'asc'
    }
    options.onFolderSortChange?.(currentFolderId.value, {
      column: sortColumn.value,
      direction: sortDirection.value,
    })
  }

  watch(searchKeyword, () => {
    // keep compatibility for direct writes from templates
    if (searchKeyword.value.trim()) scheduleSearch()
    else clearSearchResults()
  })

  function enterFolder(folderId: number) {
    applyFolderSort(folderId)
    searchKeyword.value = ''
    clearSearchResults()
    clearSelection()
    closeQuickLook()
    currentFolderId.value = folderId
    if (folderId === 0) activeNamed.value = null
    else if (locations.value.documents?.id === folderId) activeNamed.value = 'documents'
    else if (locations.value.downloads?.id === folderId) activeNamed.value = 'downloads'
    else activeNamed.value = null
    void loadFiles()
  }

  async function loadFolderItems(folderId: number): Promise<FileEntry[]> {
    const data = await fetchFileList(folderId)
    return data?.items || []
  }

  async function resetColumnStack(folderId: number, name: string) {
    if (viewMode.value !== 'column') {
      columnStack.value = []
      return
    }
    try {
      const colItems = await loadFolderItems(folderId)
      columnStack.value = [{ folderId, name, items: colItems, selectedId: null }]
    } catch {
      columnStack.value = [{ folderId, name, items: [], selectedId: null }]
    }
  }

  async function pushColumnFromFolder(item: FileEntry, columnIndex: number) {
    if (!item.is_folder) return
    const nextStack = columnStack.value.slice(0, columnIndex + 1)
    if (nextStack[columnIndex]) {
      nextStack[columnIndex] = { ...nextStack[columnIndex], selectedId: item.id }
    }
    try {
      const colItems = await loadFolderItems(item.id)
      nextStack.push({ folderId: item.id, name: item.file_name, items: colItems, selectedId: null })
    } catch {
      nextStack.push({ folderId: item.id, name: item.file_name, items: [], selectedId: null })
    }
    columnStack.value = nextStack
    // Keep primary state aligned with deepest folder
    isRecycleBin.value = false
    breadcrumb.value = [
      { id: null, name: '桌面' },
      ...nextStack
        .filter((col) => col.folderId !== 0)
        .map((col) => ({ id: col.folderId, name: col.name })),
    ]
    if (breadcrumb.value.length === 1 && nextStack[0]?.folderId === 0) {
      // desktop root only
    }
    currentFolderId.value = item.id
    selectedId.value = null
    syncWindowTitle(item.file_name)
  }

  function selectInColumn(item: FileEntry, columnIndex: number) {
    selectedId.value = item.id
    const next = columnStack.value.slice()
    if (!next[columnIndex]) return
    next[columnIndex] = { ...next[columnIndex], selectedId: item.id }
    // Selecting a file collapses deeper columns; selecting folder expands
    if (!item.is_folder) {
      columnStack.value = next.slice(0, columnIndex + 1)
      return
    }
    void pushColumnFromFolder(item, columnIndex)
  }

  function pushHistory(folderId: number, name: string) {
    navigationHistory.value = navigationHistory.value.slice(0, historyIndex.value + 1)
    navigationBreadcrumbs.value = navigationBreadcrumbs.value.slice(0, historyIndex.value + 1)
    navigationHistory.value.push({ id: folderId, name })
    navigationBreadcrumbs.value.push(breadcrumb.value.map(item => ({ ...item })))
    historyIndex.value++
  }

  function syncWindowTitle(folderName: string) {
    const windowId = options.windowId?.()
    if (!windowId) return
    // 只回写标题用 folderName，避免 folderId 回灌 props 触发 watch 截断路径栈
    windowManager.updateWindowPayload(windowId, {
      folderName,
    })
  }

  async function ensureLocations() {
    try {
      const data = await fetchFinderLocations()
      if (data && typeof data === 'object') {
        locations.value = {
          desktop: data.desktop || { key: 'desktop', id: 0, name: '桌面' },
          documents: data.documents,
          downloads: data.downloads,
          ...data,
        }
      }
    } catch {
      // keep defaults; sidebar can still open desktop/recycle
    }
  }

  async function goRoot() {
    isRecycleBin.value = false
    activeNamed.value = null
    breadcrumb.value = [{ id: null, name: '桌面' }]
    pushHistory(0, '桌面')
    enterFolder(0)
    syncWindowTitle('桌面')
    void resetColumnStack(0, '桌面')
  }

  async function openNamedLocation(key: 'documents' | 'downloads') {
    await ensureLocations()
    const loc = locations.value[key]
    if (!loc || !loc.id) {
      // fallback: still try ensure once more via API side-effect
      await ensureLocations()
    }
    const resolved = locations.value[key]
    if (!resolved?.id) return

    isRecycleBin.value = false
    activeNamed.value = key
    const label = resolved.name || (key === 'documents' ? '文稿' : '下载')
    const folderId = Number(resolved.id)
    breadcrumb.value = [{ id: null, name: '桌面' }, { id: folderId, name: label }]
    pushHistory(folderId, label)
    searchKeyword.value = ''
    selectedId.value = null
    enterFolder(folderId)
    syncWindowTitle(label)
    void resetColumnStack(folderId, label)
  }

  async function goUp() {
    if (!canGoUp.value) return
    breadcrumb.value.pop()
    const parent = breadcrumb.value[breadcrumb.value.length - 1]
    pushHistory(parent.id ?? 0, parent.name)
    enterFolder(parent.id ?? 0)
    syncWindowTitle(parent.name)
    void resetColumnStack(parent.id ?? 0, parent.name)
  }

  async function navigateToCrumb(index: number) {
    const crumb = breadcrumb.value[index]
    breadcrumb.value = breadcrumb.value.slice(0, index + 1)
    pushHistory(crumb.id ?? 0, crumb.name)
    enterFolder(crumb.id ?? 0)
    syncWindowTitle(crumb.name)
    void resetColumnStack(crumb.id ?? 0, crumb.name)
  }

  function goBack() {
    if (!canGoBack.value) return
    historyIndex.value--
    const target = navigationHistory.value[historyIndex.value]
    breadcrumb.value = navigationBreadcrumbs.value[historyIndex.value]?.map(item => ({ ...item }))
      || (target.id === 0 ? [{ id: null, name: '桌面' }] : [{ id: null, name: '桌面' }, { id: target.id, name: target.name }])
    enterFolder(target.id)
    syncWindowTitle(target.name)
    void resetColumnStack(target.id, target.name)
  }

  function goForward() {
    if (!canGoForward.value) return
    historyIndex.value++
    const target = navigationHistory.value[historyIndex.value]
    breadcrumb.value = navigationBreadcrumbs.value[historyIndex.value]?.map(item => ({ ...item }))
      || (target.id === 0 ? [{ id: null, name: '桌面' }] : [{ id: null, name: '桌面' }, { id: target.id, name: target.name }])
    enterFolder(target.id)
    syncWindowTitle(target.name)
    void resetColumnStack(target.id, target.name)
  }

  function displayName(file: FileEntry): string {
    return file.is_folder ? String(file.file_name || '') : formatFileDisplayName(file.file_name, file.format)
  }

  function setSelection(ids: number[], primaryId?: number | null) {
    const unique = Array.from(new Set(ids.filter((id) => Number.isFinite(id))))
    selectedIds.value = unique
    selectedId.value = primaryId != null
      ? primaryId
      : (unique.length ? unique[unique.length - 1] : null)
  }

  function clearSelection() {
    selectedIds.value = []
    selectedId.value = null
    selectionAnchorId.value = null
  }

  function selectItem(
    item: FileEntry,
    opts: { additive?: boolean; range?: boolean } = {},
  ) {
    const list = sortedItems.value
    if (opts.range && selectionAnchorId.value != null) {
      const a = list.findIndex((x) => x.id === selectionAnchorId.value)
      const b = list.findIndex((x) => x.id === item.id)
      if (a >= 0 && b >= 0) {
        const [from, to] = a < b ? [a, b] : [b, a]
        const rangeIds = list.slice(from, to + 1).map((x) => x.id)
        setSelection(rangeIds, item.id)
        return
      }
    }
    if (opts.additive) {
      const set = new Set(selectedIds.value)
      if (set.has(item.id)) set.delete(item.id)
      else set.add(item.id)
      const next = Array.from(set)
      setSelection(next, item.id)
      selectionAnchorId.value = item.id
      return
    }
    setSelection([item.id], item.id)
    selectionAnchorId.value = item.id
  }

  function selectAll() {
    const ids = sortedItems.value.map((item) => item.id)
    setSelection(ids, ids[ids.length - 1] ?? null)
    selectionAnchorId.value = ids[0] ?? null
  }

  function selectByIds(ids: number[], primaryId?: number | null) {
    setSelection(ids, primaryId)
    if (primaryId != null) selectionAnchorId.value = primaryId
  }

  function openQuickLook(item?: FileEntry | null) {
    const target = item || selectedItem.value
    if (!target) return
    quickLookItem.value = target
    quickLookVisible.value = true
  }

  function closeQuickLook() {
    quickLookVisible.value = false
    quickLookItem.value = null
  }

  async function toggleTagOnItem(item: FileEntry, tag: FinderTagColor) {
    await toggleItemTag(itemTypeOf(item), item.id, tag)
    tagRevision.value += 1
  }

  async function clearTagsOnItem(item: FileEntry) {
    await clearItemTags(itemTypeOf(item), item.id)
    tagRevision.value += 1
  }

  async function applyTagAction(key: string, item: FileEntry | null, items?: FileEntry[] | null) {
    const targets = (items && items.length)
      ? items
      : (item ? [item] : [])
    if (!targets.length) return false
    if (key === 'tag:clear') {
      for (const target of targets) await clearTagsOnItem(target)
      return true
    }
    if (key.startsWith('tag:')) {
      const tag = key.slice(4) as FinderTagColor
      if (!FINDER_TAGS.some((t) => t.key === tag)) return false
      for (const target of targets) await toggleTagOnItem(target, tag)
      return true
    }
    return false
  }

  async function loadTags() {
    const { loadFinderTagsFromServer } = await import('./finder-tags')
    await loadFinderTagsFromServer()
    tagRevision.value += 1
  }

  function setTagFilter(tag: FinderTagColor | null) {
    activeTagFilter.value = tag
    // 标签筛选是当前目录视图过滤，不离开当前文件夹
    clearSelection()
  }

  function openSelected() {
    if (selectedItem.value) openItem(selectedItem.value)
  }

  function openItem(item: FileEntry) {
    if (item.is_folder) {
      activeNamed.value = null
      const last = breadcrumb.value[breadcrumb.value.length - 1]
      // 深层路径持续追加；避免重复 push 同一层
      if (!last || last.id !== item.id) {
        breadcrumb.value = [
          ...breadcrumb.value,
          { id: item.id, name: item.file_name },
        ]
      } else {
        last.name = item.file_name
      }
      pushHistory(item.id, item.file_name)
      enterFolder(item.id)
      syncWindowTitle(item.file_name)
      void resetColumnStack(item.id, item.file_name)
      return
    }
    openFileByRecord({ fileId: item.id, fileName: displayName(item), format: item.format || '' })
  }

  function openRecycle() {
    isRecycleBin.value = true
    activeNamed.value = null
    breadcrumb.value = [{ id: null, name: '回收站' }]
    clearSelection()
    searchKeyword.value = ''
    columnStack.value = []
    void loadFiles()
    syncWindowTitle('回收站')
  }

  watch(viewMode, (mode) => {
    if ((mode === 'column') && !isRecycleBin.value) {
      const name = breadcrumb.value[breadcrumb.value.length - 1]?.name || '桌面'
      void resetColumnStack(currentFolderId.value, name)
    }
  })

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1048576).toFixed(1)} MB`
  }

  function showProperties(item: FileEntry) {
    propertiesItem.value = item
    propertiesVisible.value = true
  }

  function closeProperties() {
    propertiesVisible.value = false
    propertiesItem.value = null
  }

  return {
    currentFolderId,
    items,
    loadState,
    loading,
    uploadInput,
    breadcrumb,
    viewMode,
    activeNamed,
    locations,
    columnStack,
    selectedId,
    selectedIds,
    selectedItems,
    selectionAnchorId,
    quickLookVisible,
    quickLookItem,
    tagRevision,
    activeTagFilter,
    sortColumn,
    sortDirection,
    setSort,
    searchKeyword,
    searchScope,
    searchResults,
    searchLoading,
    setSearchScope,
    setSearchKeyword,
    navigationHistory,
    historyIndex,
    isRecycleBin,
    propertiesVisible,
    propertiesItem,
    folders,
    files,
    filteredItems,
    sortedItems,
    selectedItem,
    canGoUp,
    canGoBack,
    canGoForward,
    pageTitle,
    selectedSummary,
    applyInitialFolder,
    loadFiles,
    enterFolder,
    goRoot,
    goUp,
    navigateToCrumb,
    goBack,
    goForward,
    displayName,
    selectItem,
    selectAll,
    selectByIds,
    clearSelection,
    openQuickLook,
    closeQuickLook,
    tagsOf,
    toggleTagOnItem,
    clearTagsOnItem,
    applyTagAction,
    loadTags,
    setTagFilter,
    openSelected,
    openItem,
    openRecycle,
    openNamedLocation,
    ensureLocations,
    resetColumnStack,
    selectInColumn,
    pushColumnFromFolder,
    syncWindowTitle,
    formatSize,
    showProperties,
    closeProperties,
    pushHistory,
    emit,
  }
}
