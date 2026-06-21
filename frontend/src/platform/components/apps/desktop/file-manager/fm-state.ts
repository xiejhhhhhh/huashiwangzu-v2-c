import { computed, ref, watch } from 'vue'
import { fetchFileList } from '@/shared/api/desktop'
import { openFileByRecord } from '@/desktop/app-registry/app-opener'
import { useDesktopEventBus } from '@/desktop/events/use-desktop-event-bus'
import type { FileEntry } from '@/shared/api/types'
import { formatFileDisplayName } from '@/shared/files/display-name'
import type { DesktopFileManagerBreadcrumbItem, NavigationEntry } from './types'

interface CreateFileManagerStateOptions {
  folderId: () => number | undefined
  folderName: () => string | undefined
}

export function createFileManagerState(options: CreateFileManagerStateOptions) {
  const { emit, on } = useDesktopEventBus()

  const currentFolderId = ref<number>(0)
  const items = ref<FileEntry[]>([])
  const loading = ref(false)
  const uploadInput = ref<HTMLInputElement | null>(null)
  const breadcrumb = ref<DesktopFileManagerBreadcrumbItem[]>([{ id: null, name: '桌面' }])
  const viewMode = ref<'grid' | 'list'>('grid')
  const selectedId = ref<number | null>(null)

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

  async function loadFiles() {
    loading.value = true
    try {
      const res = await fetchFileList(currentFolderId.value)
      if (res.success) items.value = res.data?.items || []
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
    void loadFiles()
  }

  function pushHistory(folderId: number, name: string) {
    navigationHistory.value = navigationHistory.value.slice(0, historyIndex.value + 1)
    navigationBreadcrumbs.value = navigationBreadcrumbs.value.slice(0, historyIndex.value + 1)
    navigationHistory.value.push({ id: folderId, name })
    navigationBreadcrumbs.value.push(breadcrumb.value.map(item => ({ ...item })))
    historyIndex.value++
  }

  async function goRoot() {
    isRecycleBin.value = false
    breadcrumb.value = [{ id: null, name: '桌面' }]
    pushHistory(0, '桌面')
    enterFolder(0)
  }

  async function goUp() {
    if (!canGoUp.value) return
    breadcrumb.value.pop()
    const parent = breadcrumb.value[breadcrumb.value.length - 1]
    pushHistory(parent.id ?? 0, parent.name)
    enterFolder(parent.id ?? 0)
  }

  async function navigateToCrumb(index: number) {
    const crumb = breadcrumb.value[index]
    breadcrumb.value = breadcrumb.value.slice(0, index + 1)
    pushHistory(crumb.id ?? 0, crumb.name)
    enterFolder(crumb.id ?? 0)
  }

  function goBack() {
    if (!canGoBack.value) return
    historyIndex.value--
    const target = navigationHistory.value[historyIndex.value]
    breadcrumb.value = navigationBreadcrumbs.value[historyIndex.value]?.map(item => ({ ...item }))
      || (target.id === 0 ? [{ id: null, name: '桌面' }] : [{ id: null, name: '桌面' }, { id: target.id, name: target.name }])
    enterFolder(target.id)
  }

  function goForward() {
    if (!canGoForward.value) return
    historyIndex.value++
    const target = navigationHistory.value[historyIndex.value]
    breadcrumb.value = navigationBreadcrumbs.value[historyIndex.value]?.map(item => ({ ...item }))
      || (target.id === 0 ? [{ id: null, name: '桌面' }] : [{ id: null, name: '桌面' }, { id: target.id, name: target.name }])
    enterFolder(target.id)
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
      breadcrumb.value.push({ id: item.id, name: item.file_name })
      pushHistory(item.id, item.file_name)
      enterFolder(item.id)
      return
    }
    openFileByRecord({ fileId: item.id, fileName: displayName(item), format: item.format || '' })
  }

  function openRecycle() {
    isRecycleBin.value = true
    breadcrumb.value = [{ id: null, name: '回收站' }]
  }

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
    loading,
    uploadInput,
    breadcrumb,
    viewMode,
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
    formatSize,
    showProperties,
    closeProperties,
    pushHistory,
    emit,
  }
}
