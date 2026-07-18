import { computed, ref, watch } from 'vue'
import { fetchFileList, fetchFinderLocations, fetchRecycleBinList } from '@/shared/api/desktop'
import type { FinderLocation } from '@/shared/api/desktop'
import type { RecycleBinEntry } from '@/shared/api/types'
import { openFileByRecord } from '@/desktop/app-registry/app-opener'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import type { FileEntry } from '@/shared/api/types'
import { formatFileDisplayName } from '@/shared/files/display-name'
import type { DesktopFileManagerBreadcrumbItem, NavigationEntry } from './types'
import { createLoadState, failLoading, finishLoading, startLoading } from '@/shared/composables/use-load-state'
import { windowManager } from '@/desktop/window-manager/window-manager'

interface CreateFileManagerStateOptions {
  folderId: () => number | undefined
  folderName: () => string | undefined
  windowId?: () => string | undefined
}

export function createFileManagerState(options: CreateFileManagerStateOptions) {
  const { emit, on } = useDesktopEventBus()

  const currentFolderId = ref<number>(0)
  const items = ref<FileEntry[]>([])
  const loadState = createLoadState<FileEntry[]>([])
  const loading = ref(false)
  const uploadInput = ref<HTMLInputElement | null>(null)
  const breadcrumb = ref<DesktopFileManagerBreadcrumbItem[]>([{ id: null, name: '桌面' }])
  const viewMode = ref<'grid' | 'list' | 'column'>('grid')
  const activeNamed = ref<'documents' | 'downloads' | null>(null)
  const locations = ref<Record<string, FinderLocation>>({
    desktop: { key: 'desktop', id: 0, name: '桌面' },
  })
  const selectedId = ref<number | null>(null)
  /** Miller Columns: stack of folder columns (folderId + items + selection) */
  const columnStack = ref<Array<{ folderId: number; name: string; items: FileEntry[]; selectedId: number | null }>>([])

  const sortColumn = ref<'name' | 'date' | 'type' | 'size'>('name')
  const sortDirection = ref<'asc' | 'desc'>('asc')
  const searchKeyword = ref('')
  const navigationHistory = ref<NavigationEntry[]>([{ id: 0, name: '桌面' }])
  const navigationBreadcrumbs = ref<DesktopFileManagerBreadcrumbItem[][]>([[{ id: null, name: '桌面' }]])
  const historyIndex = ref(0)

  const isRecycleBin = ref(false)
  const propertiesVisible = ref(false)
  const propertiesItem = ref<FileEntry | null>(null)

  const folders = computed(() => items.value.filter(item => item.is_folder))
  const files = computed(() => items.value.filter(item => !item.is_folder))

  const filteredItems = computed(() => {
    let filtered = items.value
    if (searchKeyword.value) {
      const keyword = searchKeyword.value.toLowerCase()
      filtered = filtered.filter(item => item.file_name.toLowerCase().includes(keyword))
    }
    const folderList = filtered.filter(item => item.is_folder)
    const fileList = filtered.filter(item => !item.is_folder)
    const dir = sortDirection.value === 'asc' ? 1 : -1
    function sortByColumn(list: FileEntry[]): FileEntry[] {
      return [...list].sort((a, b) => {
        let cmp = 0
        switch (sortColumn.value) {
          case 'name': cmp = a.file_name.localeCompare(b.file_name); break
          case 'date': cmp = a.created_at.localeCompare(b.created_at); break
          case 'type': cmp = (a.format || '').localeCompare(b.format || ''); break
          case 'size': cmp = a.file_size - b.file_size; break
        }
        return cmp * dir
      })
    }
    return [...sortByColumn(folderList), ...sortByColumn(fileList)]
  })
  const sortedItems = filteredItems

  const selectedItem = computed(() => items.value.find(item => item.id === selectedId.value) || null)
  const canGoUp = computed(() => !isRecycleBin.value && breadcrumb.value.length > 1)
  const pageTitle = computed(() => breadcrumb.value.map(item => item.name).join(' / '))
  const selectedSummary = computed(() => selectedItem.value ? `当前选中 ${displayName(selectedItem.value)}` : '系统文件管理器')

  const canGoBack = computed(() => !isRecycleBin.value && historyIndex.value > 0)
  const canGoForward = computed(() => !isRecycleBin.value && historyIndex.value < navigationHistory.value.length - 1)

  watch(options.folderId, () => {
    applyInitialFolder()
    enterFolder(currentFolderId.value)
  })

  watch(options.folderName, () => {
    if (currentFolderId.value > 0 && breadcrumb.value.length > 1) {
      breadcrumb.value = [{ id: null, name: '桌面' }, { id: currentFolderId.value, name: options.folderName() || '文件夹' }]
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
    selectedId.value = null
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
    } catch (error: unknown) {
      failLoading(loadState, error, '文件列表加载失败')
    } finally {
      loading.value = false
    }
  }

  function enterFolder(folderId: number) {
    sortColumn.value = 'name'
    sortDirection.value = 'asc'
    searchKeyword.value = ''
    selectedId.value = null
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
    windowManager.updateWindowPayload(windowId, {
      folderId: currentFolderId.value,
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
    sortColumn.value = 'name'
    sortDirection.value = 'asc'
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

  function selectItem(item: FileEntry) {
    selectedId.value = item.id
  }

  function openSelected() {
    if (selectedItem.value) openItem(selectedItem.value)
  }

  function openItem(item: FileEntry) {
    if (item.is_folder) {
      activeNamed.value = null
      breadcrumb.value.push({ id: item.id, name: item.file_name })
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
    selectedId.value = null
    searchKeyword.value = ''
    columnStack.value = []
    void loadFiles()
    syncWindowTitle('回收站')
  }

  watch(viewMode, (mode) => {
    if (mode === 'column' && !isRecycleBin.value) {
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
    sortColumn,
    sortDirection,
    searchKeyword,
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
