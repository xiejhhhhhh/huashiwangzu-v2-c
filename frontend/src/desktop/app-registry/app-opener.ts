import { getApp } from '@/desktop/app-registry/app-registry'
import type { FileOpenPayload } from '@/desktop/window-manager/window-types'
import { useDesktopAppHandleV2 } from '@/desktop/app-registry/desktop-app-handle-v2'
import { openFileByRecord } from '@/desktop/app-registry/content-file-opener'

export { openFileByRecord, type FileOpenPayload }

/** 正式入口：按 productId / appKey 开窗口 */
export function openAppById(appId: string, payload?: Record<string, unknown>): string | null {
  const handle = useDesktopAppHandleV2()
  return handle.openApp(appId, payload ?? {})
}
