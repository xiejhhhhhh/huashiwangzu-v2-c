import { desktopMessage } from '@/desktop/feedback/desktop-feedback'
import api from '@/shared/api'
import { windowManager } from '@/desktop/window-manager/window-manager'
import { getApp } from '@/desktop/app-registry/app-registry'
import emitter from '@/desktop/events'
import { useUserStore } from '@/platform/stores/user'
import { getOpenWindowFailureMessage } from './app-visibility'
import { openFileByRecord } from './content-file-opener'
import { registerActionHandler, unregisterAppHandlers, routeRequest, getRegisteredAppIds, getRegisteredActions } from './action-registry'
import { standardActionDef } from './types-app-handle-v2'
import { generateRequestId, registerPendingRequest } from './request-response-channel'
import type { appId, windowId, WindowHandle, CrossAppActionResponse, ActionHandlerDeclaration, DataHandlerDeclaration, CommandOptions, NotificationPayload } from './types-app-handle-v2'

export function useDesktopAppHandleV2() {
  const userStore = useUserStore()

  function checkPermission(appId: appId): appId | null {
    const app = getApp(appId)
    if (!app) { desktopMessage.warning(`应用「${appId}」不存在`); return null }
    if (app.enabled === false) { desktopMessage.warning(`应用「${app.appName}」已停用`); return null }
    const currentRole = userStore.userInfo?.role?.toLowerCase()
    if (app.allowedRoles && currentRole && !app.allowedRoles.includes(currentRole)) {
      desktopMessage.warning(`您无权访问应用「${app.appName}」`)
      return null
    }
    return appId
  }

  async function auditCheck(action: string, params: Record<string, unknown>, target: appId): Promise<void> {
    const def = standardActionDef[action as keyof typeof standardActionDef]
    if (def && (def.auditLevel === 'medium' || def.auditLevel === 'high')) {
      try {
        await api.post('/desktop/audit-log', { action, params, target_app: target })
      } catch {
        console.warn('Failed to write audit log, continuing')
      }
    }
  }

  function openApp(appId: appId, params?: Record<string, unknown>): windowId | null {
    const ok = checkPermission(appId)
    if (!ok) return null
    const windowId = windowManager.openWindow(appId, params)
    if (!windowId) desktopMessage.info(getOpenWindowFailureMessage(getApp(appId)))
    return windowId
  }

  async function openFile(fileId: number, format?: string, options?: CommandOptions): Promise<WindowHandle | null> {
    // 正式路径：只走 Content Open Resolver
    openFileByRecord({ fileId, fileName: '', format: format || '' })
    return { windowId: '', appId: '' }
  }

  async function sendCommand(
    targetAppId: appId, action: string, params?: Record<string, unknown>, options?: CommandOptions
  ): Promise<CrossAppActionResponse> {
    const ok = checkPermission(targetAppId)
    if (!ok) return { success: false, error: { code: 'ERR_PERMISSION_DENIED', message: 'Permission denied' } }
    await auditCheck(action, params || {}, targetAppId)
    const requestId = generateRequestId()
    const timeout = options?.timeout || standardActionDef[action as keyof typeof standardActionDef]?.defaultTimeout || 10000
    const result = registerPendingRequest(requestId, timeout, () => ({
      success: false, error: { code: 'ERR_TIMEOUT', message: 'Request timed out' }
    }))
    emitter.emit('app:request', { targetAppId, action, params: params || {}, requestId } as never)
    return result
  }

  async function requestData(
    targetAppId: appId, type: string, filter?: Record<string, unknown>, options?: CommandOptions
  ): Promise<CrossAppActionResponse> {
    return sendCommand(targetAppId, `data:${type}`, filter, options)
  }

  function subscribeEvent(eventName: string, handler: (payload: unknown) => void): () => void {
    emitter.on(eventName as never, handler as never)
    return () => { emitter.off(eventName as never, handler as never) }
  }

  function unsubscribeEvent(eventName: string, handler?: (payload: unknown) => void): void {
    if (handler) {
      emitter.off(eventName as never, handler as never)
    }
  }

  function broadcastEvent(eventName: string, payload?: unknown): void {
    emitter.emit(eventName as never, payload as never)
  }

  function notifyUser(payload: NotificationPayload): void {
    const kind = payload.type || 'info'
    if (kind === 'success') desktopMessage.success(payload.message)
    else if (kind === 'warning') desktopMessage.warning(payload.message)
    else if (kind === 'error') desktopMessage.error(payload.message)
    else desktopMessage.info(payload.message)
    if (payload.targetApp) {
      emitter.emit('app:notification' as never, payload as never)
    }
  }

  function registerDataHandler(decl: DataHandlerDeclaration) {
    registerActionHandler({ appKey: decl.appKey, action: `data:${decl.dataType}`, handler: async (params, metadata) => {
      const result = await decl.handler(params, metadata)
      return { success: true, data: result.data }
    }})
  }

  return {
    openApp,
    openFile,
    sendCommand,
    requestData,
    subscribeEvent,
    unsubscribeEvent,
    broadcastEvent,
    notifyUser,
    registerActionHandler,
    registerDataHandler,
    unregisterAppHandlers,
     routeRequest: (appId: appId, action: string, params: Record<string, unknown>) =>
       routeRequest(appId, action, params, { sourceAppId: '', sourceWindowId: '', requestId: generateRequestId() }),
     getRegisteredAppIds,
     getRegisteredActions,
   }
}
