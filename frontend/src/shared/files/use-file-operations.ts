import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/shared/api'
import {
  createFileRequest, uploadFileRequest, renameEntryRequest,
  moveToRecycleBinRequest, moveEntryRequest, copyEntryRequest, downloadFileRequest,
  batchDeleteRequest, batchMoveRequest, resolveNameConflictRequest,
} from '@/shared/api/desktop'
import { formatFileDisplayName } from '@/shared/files/display-name'
import type { FileEntry } from '@/shared/api/types'

export type FileItemType = 'file' | 'folder'

export interface ClipboardLike {
  id: number
  type: FileItemType
  name: string
}

export interface BatchOperationError {
  id?: number | string
  name?: string
  message: string
}

export interface BatchOperationResult {
  successCount: number
  failCount: number
  errors: BatchOperationError[]
  /** copy new ids when API returns them */
  created?: Array<{ id: number; type: FileItemType }>
  renamed?: { id: number; type: FileItemType; prevName: string; nextName: string }
}

export type ConflictAction = 'replace' | 'keep_both' | 'skip' | 'cancel'

async function askNameConflict(
  name: string,
  mode: 'move' | 'copy',
  opts?: { multi?: boolean },
): Promise<ConflictAction | 'replace_all' | 'keep_both_all'> {
  const multiHint = opts?.multi ? '\n（多选冲突：确定=全部替换，取消=全部保留两者）' : ''
  try {
    await ElMessageBox.confirm(
      `目标已有同名项目「${name}」。\n选择「替换」将把已有项目移入回收站；「保留两者」会自动重命名。${multiHint}`,
      mode === 'move' ? '移动冲突' : '复制冲突',
      {
        distinguishCancelAndClose: true,
        confirmButtonText: opts?.multi ? '全部替换' : '替换',
        cancelButtonText: opts?.multi ? '全部保留两者' : '保留两者',
        type: 'warning',
        showClose: true,
      },
    )
    return opts?.multi ? 'replace_all' : 'replace'
  } catch (action) {
    if (action === 'cancel') return opts?.multi ? 'keep_both_all' : 'keep_both'
    return 'cancel'
  }
}

function isConflictError(error: unknown): boolean {
  const err = error as { http_status?: number; response?: { status?: number }; message?: string; error?: string } | null
  const status = err?.http_status || err?.response?.status
  if (status === 409) return true
  const msg = String(err?.message || err?.error || error || '')
  return msg.includes('409') || msg.includes('same name') || msg.includes('同名')
}

/** 统一文件全名：文件夹用原名，文件用显示名（含扩展名） */
export function fullFileName(file: FileEntry): string {
  return file.is_folder
    ? String(file.file_name || '')
    : formatFileDisplayName(file.file_name, file.format)
}

function createBatchOperationResult(): BatchOperationResult {
  return { successCount: 0, failCount: 0, errors: [] }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function stringField(source: Record<string, unknown>, key: string): string | null {
  const value = source[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message
  if (!isRecord(error)) return '操作失败'

  const direct = stringField(error, 'error') || stringField(error, 'message')
  if (direct) return direct

  const data = error.data
  if (isRecord(data)) {
    const dataMessage = stringField(data, 'error') || stringField(data, 'message')
    if (dataMessage) return dataMessage
  }

  const response = error.response
  if (isRecord(response) && isRecord(response.data)) {
    const responseMessage = stringField(response.data, 'error') || stringField(response.data, 'message')
    if (responseMessage) return responseMessage
  }

  return '操作失败'
}

function formatBatchError(error: BatchOperationError): string {
  const label = error.name || (error.id !== undefined ? `#${String(error.id)}` : '未知项目')
  return `${label}: ${error.message}`
}

function showBatchOperationResult(actionLabel: string, successText: string, result: BatchOperationResult) {
  const totalCount = result.successCount + result.failCount
  if (totalCount === 0) return

  if (result.failCount === 0) {
    ElMessage.success(totalCount > 1 ? `全部成功：完成 ${totalCount} 个` : `全部成功：${successText}`)
    return
  }

  const detail = result.errors.slice(0, 3).map(formatBatchError).join('；')
  const suffix = detail ? `：${detail}${result.errors.length > 3 ? ' 等' : ''}` : ''
  console.warn(`[FileOperations] ${actionLabel} failed items`, result.errors)

  if (result.successCount > 0) {
    ElMessage.warning({
      message: `部分成功：完成 ${result.successCount} 个，失败 ${result.failCount} 个${suffix}`,
      duration: 6000,
      showClose: true,
    })
    return
  }

  ElMessage.error({
    message: `全部失败：${result.failCount} 个项目未完成${suffix}`,
    duration: 6000,
    showClose: true,
  })
}

export interface FileOperationsOptions {
  /** 操作成功后的刷新回调，由调用方注入自己的刷新逻辑 */
  refresh: () => void | Promise<void>
}

export function useFileOperations(options: FileOperationsOptions) {
  const refresh = async () => { await options.refresh() }

  async function uploadFile(file: File, folderId: number | null): Promise<boolean> {
    try {
      await uploadFileRequest(file, folderId ?? undefined)
      ElMessage.success('上传成功')
      await refresh()
      return true
    } catch {
      ElMessage.warning('上传失败')
      return false
    }
  }

  async function createFolder(parentId: number | null): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      if (!value) return
      await api.post('/files/folder', { name: value, parent_id: parentId })
      ElMessage.success('已创建')
      await refresh()
    } catch { /* cancelled */ }
  }

  async function createFile(ext: string, folderId: number | null, label: string): Promise<void> {
    try {
      await createFileRequest(label, ext, folderId)
      ElMessage.success(`已创建 ${label}`)
      await refresh()
    } catch {
      ElMessage.warning('创建失败')
    }
  }

  async function downloadFile(file: FileEntry): Promise<void> {
    try {
      await downloadFileRequest(file.id, fullFileName(file))
    } catch {
      ElMessage.warning('下载失败')
    }
  }

  async function copyPath(file: FileEntry): Promise<void> {
    try {
      await navigator.clipboard.writeText(fullFileName(file))
      ElMessage.success('已复制路径')
    } catch {
      ElMessage.warning('复制失败')
    }
  }

  async function renameEntry(file: FileEntry): Promise<BatchOperationResult | null> {
    const result = createBatchOperationResult()
    try {
      const { value } = await ElMessageBox.prompt('输入新名称', '重命名', {
        inputValue: file.file_name, confirmButtonText: '确定', cancelButtonText: '取消',
      })
      if (!value || value === file.file_name) return null
      try {
        await renameEntryRequest(file.is_folder ? 'folder' : 'file', file.id, value)
      } catch (error: unknown) {
        if (isConflictError(error)) {
          ElMessage.warning('该名称已存在')
          result.failCount = 1
          return result
        }
        throw error
      }
      result.successCount = 1
      result.renamed = {
        id: file.id,
        type: file.is_folder ? 'folder' : 'file',
        prevName: file.file_name,
        nextName: value,
      }
      ElMessage.success('重命名成功')
      await refresh()
      return result
    } catch {
      return null
    }
  }

  async function deleteEntry(file: FileEntry): Promise<BatchOperationResult | null> {
    try {
      await ElMessageBox.confirm(`确定删除 "${file.file_name}"？`, '确认删除', { type: 'warning' })
    } catch {
      return null
    }
    const result = createBatchOperationResult()
    try {
      await moveToRecycleBinRequest(file.is_folder ? 'folder' : 'file', file.id)
      result.successCount += 1
      showBatchOperationResult('删除', '已移至回收站', result)
      await refresh()
    } catch (error: unknown) {
      result.failCount += 1
      result.errors.push({ id: file.id, name: fullFileName(file), message: errorMessage(error) })
      showBatchOperationResult('删除', '已移至回收站', result)
    }
    return result
  }

  async function pasteToFolder(folderId: number | null, items: ClipboardLike[], isCut: boolean): Promise<BatchOperationResult> {
    const result = createBatchOperationResult()
    result.created = []
    let applyAll: ConflictAction | null = null
    for (const item of items) {
      try {
        if (isCut) {
          await moveEntryRequest(item.type, item.id, folderId)
        } else {
          const resp = await copyEntryRequest(item.type, item.id, folderId)
          const newId = Number((resp as { id?: number })?.id)
          if (Number.isFinite(newId)) result.created.push({ id: newId, type: item.type })
        }
        result.successCount += 1
      } catch (error: unknown) {
        if (isConflictError(error)) {
          let action: ConflictAction | 'replace_all' | 'keep_both_all' = applyAll
            || await askNameConflict(item.name, isCut ? 'move' : 'copy', { multi: items.length > 1 })
          if (action === 'cancel') {
            result.failCount += 1
            result.errors.push({ id: item.id, name: item.name, message: '已取消' })
            break
          }
          if (action === 'replace_all') {
            applyAll = 'replace'
            action = 'replace'
          } else if (action === 'keep_both_all') {
            applyAll = 'keep_both'
            action = 'keep_both'
          } else if (items.length > 1 && !applyAll && action !== 'skip') {
            applyAll = action
          }
          if (action === 'skip') {
            result.failCount += 1
            result.errors.push({ id: item.id, name: item.name, message: '已跳过' })
            continue
          }
          try {
            const resolved = await resolveNameConflictRequest({
              action: action === 'replace' ? 'replace' : 'keep_both',
              mode: isCut ? 'move' : 'copy',
              item_type: item.type,
              item_id: item.id,
              target_folder_id: folderId,
            })
            result.successCount += 1
            const newId = Number((resolved as { new_id?: number })?.new_id)
            if (Number.isFinite(newId) && !isCut) result.created!.push({ id: newId, type: item.type })
          } catch (e2: unknown) {
            result.failCount += 1
            result.errors.push({ id: item.id, name: item.name, message: errorMessage(e2) })
          }
          continue
        }
        result.failCount += 1
        result.errors.push({ id: item.id, name: item.name, message: errorMessage(error) })
      }
    }

    showBatchOperationResult(isCut ? '移动' : '粘贴', isCut ? '已移动' : '已粘贴', result)
    if (result.successCount > 0) {
      await refresh()
    }
    return result
  }

  async function deleteEntries(files: FileEntry[]): Promise<BatchOperationResult | null> {
    if (!files.length) return null
    const label = files.length === 1
      ? `确定删除 “${files[0].file_name}”？`
      : `确定删除选中的 ${files.length} 个项目？`
    try {
      await ElMessageBox.confirm(label, '确认删除', { type: 'warning' })
    } catch {
      return null
    }
    const result = createBatchOperationResult()
    try {
      const resp = await batchDeleteRequest(
        files.map((file) => ({
          id: file.id,
          item_type: file.is_folder ? 'folder' as const : 'file' as const,
        })),
      )
      result.successCount = Number(resp.success_count || 0)
      result.failCount = Number(resp.failed_count || 0)
      for (const item of resp.items || []) {
        if (!item.success) {
          result.errors.push({
            id: item.id,
            name: `#${item.id}`,
            message: item.error || '删除失败',
          })
        }
      }
    } catch (error: unknown) {
      for (const file of files) {
        try {
          await moveToRecycleBinRequest(file.is_folder ? 'folder' : 'file', file.id)
          result.successCount += 1
        } catch (err: unknown) {
          result.failCount += 1
          result.errors.push({ id: file.id, name: fullFileName(file), message: errorMessage(err) })
        }
      }
      if (!result.successCount && !result.failCount) {
        result.failCount = files.length
        result.errors.push({ message: errorMessage(error) })
      }
    }
    showBatchOperationResult('删除', '已移至回收站', result)
    if (result.successCount > 0) await refresh()
    return result
  }

  async function moveEntries(files: FileEntry[], targetFolderId: number | null): Promise<BatchOperationResult> {
    const result = createBatchOperationResult()
    if (!files.length) return result
    const normalizedTarget = targetFolderId && targetFolderId > 0 ? targetFolderId : null
    try {
      const resp = await batchMoveRequest(
        files.map((file) => ({
          id: file.id,
          item_type: file.is_folder ? 'folder' as const : 'file' as const,
        })),
        normalizedTarget,
      )
      result.successCount = Number(resp.success_count || 0)
      result.failCount = Number(resp.failed_count || 0)
      for (const item of resp.items || []) {
        if (!item.success) {
          result.errors.push({
            id: item.id,
            name: `#${item.id}`,
            message: item.error || '移动失败',
          })
        }
      }
    } catch {
      for (const file of files) {
        try {
          await moveEntryRequest(file.is_folder ? 'folder' : 'file', file.id, normalizedTarget)
          result.successCount += 1
        } catch (error: unknown) {
          result.failCount += 1
          result.errors.push({ id: file.id, name: fullFileName(file), message: errorMessage(error) })
        }
      }
    }
    showBatchOperationResult('移动', '已移动', result)
    if (result.successCount > 0) await refresh()
    return result
  }

  return {
    uploadFile, createFolder, createFile, downloadFile,
    copyPath, renameEntry, deleteEntry, deleteEntries, moveEntries, pasteToFolder, fullFileName,
  }
}
