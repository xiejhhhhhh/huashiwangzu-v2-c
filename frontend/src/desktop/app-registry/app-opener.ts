import { ElMessage } from 'element-plus'
import { getApp } from '@/desktop/app-registry/app-registry'
import { getAppByFileFormat } from '@/desktop/app-registry/file-association-registry'
import type { FileOpenPayload } from '@/desktop/window-manager/window-types'
import { useUserStore } from '@/platform/stores/user'
import { useDesktopAppHandleV2 } from '@/desktop/app-registry/desktop-app-handle-v2'

export type { FileOpenPayload }

/**
 * Open app window by appKey with permission check via V2 handle
 */
export function openAppById(appId: string, payload?: Record<string, unknown>): string | null {
  const handle = useDesktopAppHandleV2()
  return handle.openApp(appId, payload ?? {})
}

/**
 * Open app window by file record.
 * Uses file association dispatcher to auto-match the app.
 */
export function openFileByRecord(fileRecord: FileOpenPayload): string | null {
  const { fileId, fileName, format, page } = fileRecord
  if (!fileId) {
    ElMessage.warning('Cannot open file: file ID is empty')
    return null
  }
  if (!format) {
    ElMessage.warning(`当前没有可打开该文件的软件`)
    return null
  }

  const userStore = useUserStore()
  const currentRole = userStore.userInfo?.role || 'viewer'
  const association = getAppByFileFormat(format, currentRole)

  if (!association) {
    ElMessage.warning(`当前没有可打开 .${format} 文件的软件`)
    return null
  }

  const app = getApp(association.appKey)
  if (!app) {
    ElMessage.warning(`当前没有可打开 .${format} 文件的软件`)
    return null
  }

  const handle = useDesktopAppHandleV2()
  const payload: Record<string, unknown> = {
    fileId,
    fileName,
    format,
    mode: association.editable ? 'edit' : 'view',
  }
  if (page !== undefined) payload.page = page
  return handle.openApp(association.appKey, payload)
}
