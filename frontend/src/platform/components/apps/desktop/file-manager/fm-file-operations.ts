import { useFileOperations } from '@/shared/files/use-file-operations'
import { useCreatableFormats } from '@/shared/composables/use-creatable-formats'
import { copyItems, cutItems, hasContent, currentClipboardType, currentClipboardItems, clearClipboard } from '@/desktop/clipboard/clipboard-state'
import { compressEntriesRequest } from '@/shared/api/desktop'
import { pushUndo } from './finder-undo-stack'
import type { FileEntry } from '@/shared/api/types'
import type { ComputedRef, Ref } from 'vue'
import { ElMessage } from 'element-plus'

interface FileOperationsDeps {
  uploadInput: Ref<HTMLInputElement | null>
  currentFolderId: Ref<number>
  selectedItems: ComputedRef<FileEntry[]> | Ref<FileEntry[]>
  loadFiles: () => Promise<void>
  displayName: (file: FileEntry) => string
  openItem: (item: FileEntry) => void
  showProperties: (item: FileEntry) => void
  clearSelection?: () => void
  emit: {
    (event: 'refresh:file-list', payload: { folderId: number }): void
  }
}

function toClipboardItem(file: FileEntry) {
  return {
    id: file.id,
    type: (file.is_folder ? 'folder' : 'file') as 'folder' | 'file',
    name: file.file_name,
  }
}

function resolveActionTargets(file: FileEntry | null, selected: FileEntry[]): FileEntry[] {
  if (file && selected.some((item) => item.id === file.id) && selected.length > 1) {
    return selected
  }
  if (file) return [file]
  return selected
}

export function createFileOperations(deps: FileOperationsDeps) {
  const { creatableFormats } = useCreatableFormats()

  const ops = useFileOperations({
    refresh: async () => {
      await deps.loadFiles()
      deps.emit('refresh:file-list', { folderId: deps.currentFolderId.value })
    },
  })

  function triggerUpload() {
    deps.uploadInput.value?.click()
  }

  async function onUploadFile(e: Event) {
    const input = e.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    input.value = ''
    await ops.uploadFile(file, deps.currentFolderId.value || null)
  }

  async function createFolder() {
    await ops.createFolder(deps.currentFolderId.value || null)
  }

  async function createFileFromMenuKey(key: string) {
    const ext = key.slice('create-file:'.length)
    const fmt = creatableFormats.value.find(format => format.extension === ext)
    const label = fmt?.label || `.${ext}`
    await ops.createFile(ext, deps.currentFolderId.value || null, label)
  }

  async function downloadFile(file: FileEntry) {
    await ops.downloadFile(file)
  }

  async function copyPath(file: FileEntry) {
    await ops.copyPath(file)
  }

  async function renameEntry(file: FileEntry) {
    await ops.renameEntry(file)
  }

  async function deleteEntry(file: FileEntry) {
    await ops.deleteEntry(file)
  }

  async function deleteEntries(files: FileEntry[]) {
    const snapshot = files.map((f) => ({
      id: f.id,
      type: (f.is_folder ? 'folder' : 'file') as 'folder' | 'file',
    }))
    const result = await ops.deleteEntries(files)
    if (result && result.successCount > 0) {
      pushUndo({ kind: 'delete', items: snapshot })
      deps.clearSelection?.()
    }
    return result
  }

  async function moveEntries(files: FileEntry[], targetFolderId: number | null) {
    const from = deps.currentFolderId.value || null
    const snapshot = files.map((f) => ({
      id: f.id,
      type: (f.is_folder ? 'folder' : 'file') as 'folder' | 'file',
      from,
      to: targetFolderId,
    }))
    const result = await ops.moveEntries(files, targetFolderId)
    if (result.successCount > 0) {
      pushUndo({ kind: 'move', items: snapshot })
      deps.clearSelection?.()
    }
    return result
  }

  async function compressEntries(files: FileEntry[]) {
    if (!files.length) return
    try {
      const { blob, filename } = await compressEntriesRequest(
        files.map((f) => ({ id: f.id, item_type: f.is_folder ? 'folder' : 'file' })),
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || '归档.zip'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      ElMessage.success(files.length > 1 ? `已压缩 ${files.length} 项` : '已压缩')
    } catch {
      ElMessage.warning('压缩失败')
    }
  }

  async function handleAction(key: string, file: FileEntry | null) {
    const selected = deps.selectedItems.value || []
    const targets = resolveActionTargets(file, selected)

    if (key === 'refresh') { await deps.loadFiles(); return }
    if (key === 'upload-file' || key === 'upload-here') { triggerUpload(); return }
    if (key === 'create-folder' || key === 'create-folder-here') { await createFolder(); return }
    if (key.startsWith('create-file:')) {
      await createFileFromMenuKey(key)
      return
    }
    if (key === 'paste' || key === 'paste-here') {
      if (hasContent.value) {
        const isCut = currentClipboardType.value === 'cut'
        const folderId = (file && file.is_folder) ? file.id : deps.currentFolderId.value
        const clip = currentClipboardItems.value
        await ops.pasteToFolder(folderId, clip, isCut)
        if (isCut) {
          pushUndo({
            kind: 'move',
            items: clip.map((c) => ({
              id: c.id,
              type: c.type,
              from: folderId,
              to: deps.currentFolderId.value || null,
            })),
          })
          clearClipboard()
        } else {
          // copy: cannot know new ids without API response; skip precise undo
        }
      }
      return
    }
    if (key === 'properties' || key === 'details') {
      if (file) deps.showProperties(file)
      return
    }
    if (key === 'delete') {
      if (!targets.length) return
      await deleteEntries(targets)
      return
    }
    if (key === 'cut') {
      if (!targets.length) return
      cutItems(targets.map(toClipboardItem))
      return
    }
    if (key === 'copy') {
      if (!targets.length) return
      copyItems(targets.map(toClipboardItem))
      return
    }
    if (key === 'duplicate') {
      if (!targets.length) return
      // copy into current folder (Finder "Duplicate")
      await ops.pasteToFolder(
        deps.currentFolderId.value || null,
        targets.map(toClipboardItem),
        false,
      )
      return
    }
    if (key === 'compress') {
      if (!targets.length) return
      await compressEntries(targets)
      return
    }
    if (!file) return
    if (key === 'open') { deps.openItem(file); return }
    if (key === 'download') { await downloadFile(file); return }
    if (key === 'copy-path') { await copyPath(file); return }
    if (key === 'rename') {
      const prev = file.file_name
      await renameEntry(file)
      // best-effort: renameEntry prompts; if success list refreshes — we can't know new name here without return
      void prev
      return
    }
  }

  return {
    triggerUpload,
    onUploadFile,
    createFolder,
    createFileFromMenuKey,
    downloadFile,
    copyPath,
    renameEntry,
    deleteEntry,
    deleteEntries,
    moveEntries,
    handleAction,
  }
}
