import { desktopMessage } from '@/desktop/feedback/desktop-feedback'
import { getApp } from '@/desktop/app-registry/app-registry'
import { windowManager } from '@/desktop/window-manager/window-manager'
import { openContent } from '@/shared/api/content-runtime'
import type { FileOpenPayload } from '@/desktop/window-manager/window-types'

export type { FileOpenPayload }

export function openFileByRecord(fileRecord: FileOpenPayload): string | null {
  const { fileId, fileName, format, page } = fileRecord
  if (!fileId) {
    desktopMessage.warning('无法打开：文件 ID 为空')
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
        desktopMessage.warning(
          resolution.readonlyReason
          || (format ? `没有可打开 .${format} 的产品` : '没有可打开该文件的产品'),
        )
        return
      }

      const productId = resolution.productId
      if (!getApp(productId)) {
        desktopMessage.warning(`产品「${productId}」未注册到桌面`)
        return
      }

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

      const windowId = windowManager.openWindow(productId, payload)
      if (!windowId) desktopMessage.warning(`无法打开产品「${productId}」`)
    } catch (err) {
      console.error('[openFileByRecord] resolver failed', err)
      desktopMessage.error('打开文件失败（Content Open Resolver）')
    }
  })()

  return null
}
