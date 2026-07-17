import { ElMessage } from 'element-plus'
import { getApp } from '@/desktop/app-registry/app-registry'
import type { FileOpenPayload } from '@/desktop/window-manager/window-types'
import { useDesktopAppHandleV2 } from '@/desktop/app-registry/desktop-app-handle-v2'
import { openContent } from '@/shared/api/content-runtime'

export type { FileOpenPayload }

/** 正式入口：按 productId / appKey 开窗口 */
export function openAppById(appId: string, payload?: Record<string, unknown>): string | null {
  const handle = useDesktopAppHandleV2()
  return handle.openApp(appId, payload ?? {})
}

/**
 * 正式入口：文件打开只走 Content Open Resolver。
 * 不再降级旧后缀 registry。
 */
export function openFileByRecord(fileRecord: FileOpenPayload): string | null {
  const { fileId, fileName, format, page } = fileRecord
  if (!fileId) {
    ElMessage.warning('无法打开：文件 ID 为空')
    return null
  }

  void (async () => {
    try {
      const resolution = await openContent({
        resolverVersion: 'v1',
        requestId: `open_${fileId}_${Date.now()}`,
        source: { fileId },
        requestedMode: 'view',
      })

      if (resolution.outcome !== 'resolved' || !resolution.productId) {
        ElMessage.warning(
          resolution.readonlyReason
          || (format ? `没有可打开 .${format} 的产品` : '没有可打开该文件的产品'),
        )
        return
      }

      const productId = resolution.productId
      if (!getApp(productId)) {
        ElMessage.warning(`产品「${productId}」未注册到桌面`)
        return
      }

      const handle = useDesktopAppHandleV2()
      const pkg = (resolution.package || {}) as Record<string, unknown>
      const ver = (resolution.version || {}) as Record<string, unknown>
      const session = (resolution.session || {}) as Record<string, unknown>
      const payload: Record<string, unknown> = {
        fileId,
        fileName: fileName || resolution.title || '',
        format: format || resolution.format || '',
        mode: resolution.grantedMode || 'view',
        packageId: pkg.packageId ?? session.packageId,
        versionId: ver.version_id ?? ver.versionId ?? session.versionId,
        resolutionId: resolution.resolutionId,
        adapterId: resolution.adapterId,
        readonlyReason: resolution.readonlyReason,
        productId,
      }
      if (page !== undefined) payload.page = page

      const win = handle.openApp(productId, payload)
      if (!win) {
        ElMessage.warning(`无法打开产品「${productId}」`)
      }
    } catch (err) {
      console.error('[openFileByRecord] resolver failed', err)
      ElMessage.error('打开文件失败（Content Open Resolver）')
    }
  })()

  return null
}
