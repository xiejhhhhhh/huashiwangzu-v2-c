import { createFileManagerState } from './fm-state'
import { createFileOperations } from './fm-file-operations'
import { usePermission } from '@/shared/composables/use-permission'
import { computed } from 'vue'

interface UseFileManagerStateOptions {
  folderId: () => number | undefined
  folderName: () => string | undefined
  windowId?: () => string | undefined
}

export function useFileManagerState(options: UseFileManagerStateOptions) {
  const { isEditorOrAbove } = usePermission()
  const canWrite = computed(() => isEditorOrAbove.value)

  // Core state + navigation
  const state = createFileManagerState(options)

  // File operations
  const ops = createFileOperations({
    uploadInput: state.uploadInput,
    currentFolderId: state.currentFolderId,
    loadFiles: state.loadFiles,
    displayName: state.displayName,
    openItem: state.openItem,
    showProperties: state.showProperties,
    emit: state.emit,
  })

  return {
    currentFolderId: state.currentFolderId,
    items: state.items,
    loadState: state.loadState,
    loading: state.loading,
    uploadInput: state.uploadInput,
    breadcrumb: state.breadcrumb,
    viewMode: state.viewMode,
    activeNamed: state.activeNamed,
    locations: state.locations,
    columnStack: state.columnStack,
    selectedId: state.selectedId,
    sortColumn: state.sortColumn,
    sortDirection: state.sortDirection,
    searchKeyword: state.searchKeyword,
    navigationHistory: state.navigationHistory,
    historyIndex: state.historyIndex,
    isRecycleBin: state.isRecycleBin,
    propertiesVisible: state.propertiesVisible,
    propertiesItem: state.propertiesItem,
    canWrite,
    folders: state.folders,
    files: state.files,
    filteredItems: state.filteredItems,
    sortedItems: state.sortedItems,
    selectedItem: state.selectedItem,
    canGoUp: state.canGoUp,
    canGoBack: state.canGoBack,
    canGoForward: state.canGoForward,
    pageTitle: state.pageTitle,
    selectedSummary: state.selectedSummary,
    applyInitialFolder: state.applyInitialFolder,
    loadFiles: state.loadFiles,
    enterFolder: state.enterFolder,
    goRoot: state.goRoot,
    goUp: state.goUp,
    navigateToCrumb: state.navigateToCrumb,
    goBack: state.goBack,
    goForward: state.goForward,
    displayName: state.displayName,
    selectItem: state.selectItem,
    openSelected: state.openSelected,
    openItem: state.openItem,
    openRecycle: state.openRecycle,
    openNamedLocation: state.openNamedLocation,
    ensureLocations: state.ensureLocations,
    resetColumnStack: state.resetColumnStack,
    selectInColumn: state.selectInColumn,
    pushColumnFromFolder: state.pushColumnFromFolder,
    syncWindowTitle: state.syncWindowTitle,
    formatSize: state.formatSize,
    showProperties: state.showProperties,
    closeProperties: state.closeProperties,
    handleAction: ops.handleAction,
    triggerUpload: ops.triggerUpload,
    onUploadFile: ops.onUploadFile,
    createFolder: ops.createFolder,
    createFileFromMenuKey: ops.createFileFromMenuKey,
    downloadFile: ops.downloadFile,
    copyPath: ops.copyPath,
    renameEntry: ops.renameEntry,
    deleteEntry: ops.deleteEntry,
  }
}
