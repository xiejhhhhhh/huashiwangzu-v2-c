import { ElMessage } from 'element-plus'
import { API_BASE_URL } from '@/shared/api'
import { 窗口管理器 } from '@/desktop/window-manager/window-manager'
import { getApp } from '@/desktop/app-registry/app-registry'
import { getAppByFileFormat } from '@/desktop/app-registry/file-association-registry'
import emitter from '@/desktop/events'
import { useUserStore } from '@/platform/stores/user'
import { registerActionHandler, unregisterAppHandlers, routeRequest, getRegisteredAppIds, getRegisteredActions } from './action-registry'
import { standardActionDef } from './types-app-handle-v2'
import { generateRequestId, registerPendingRequest } from './request-response-channel'
import type { appId, windowId, WindowHandle, CrossAppActionResponse, ActionHandlerDeclaration, DataHandlerDeclaration, CommandOptions, NotificationPayload } from './types-app-handle-v2'

export function useDesktopAppHandleV2() {
  const 用户Store = useUserStore()

  function checkPermission(应用标识: appId): appId | null {
    const 应用 = getApp(应用标识)
    if (!应用) { ElMessage.warning(`应用「${应用标识}」不存在`); return null }
    if (应用.enabled === false) { ElMessage.warning(`应用「${应用.appName}」已停用`); return null }
    const 当前角色 = 用户Store.用户信息?.role?.toLowerCase()
    if (应用.allowedRoles && 当前角色 && !应用.allowedRoles.includes(当前角色)) {
      ElMessage.warning(`您无权访问应用「${应用.appName}」`)
      return null
    }
    return 应用标识
  }

  async function auditCheck(动作: string, 参数: Record<string, unknown>, 目标: appId): Promise<void> {
    const 定义 = standardActionDef[动作 as keyof typeof standardActionDef]
    if (定义 && (定义.AuditLevel === 'medium' || 定义.AuditLevel === 'high')) {
      try {
        await fetch(`${API_BASE_URL}/desktop/audit-log`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 动作, params: 参数, target_app: 目标 }),
        })
      } catch {
        console.warn('审计日志记录失败，继续执行')
      }
    }
  }

  function openApp(应用标识: appId, 参数?: Record<string, unknown>): windowId | null {
    const 检查 = checkPermission(应用标识)
    if (!检查) return null
    return 窗口管理器.打开窗口(应用标识, 参数)
  }

  async function openFile(文件id: number, 格式?: string, 选项?: CommandOptions): Promise<WindowHandle | null> {
    const 关联 = getAppByFileFormat(格式 || '', 用户Store.用户信息?.role)
    if (!关联 || !关联.appKey) {
      ElMessage.warning(`无应用支持打开 ${格式} 格式`)
      return null
    }
    const 窗口ID = 窗口管理器.打开窗口(关联.appKey, { 文件id, 格式 })
    return 窗口ID ? { windowId: 窗口ID, appId: 关联.appKey } : null
  }

  async function sendCommand(
    目标appId: appId, 动作: string, 参数?: Record<string, unknown>, 选项?: CommandOptions
  ): Promise<CrossAppActionResponse> {
    const 检查 = checkPermission(目标appId)
    if (!检查) return { success: false, error: { code: 'ERR_PERMISSION_DENIED', message: '权限不足' } }
    await auditCheck(动作, 参数 || {}, 目标appId)
    const 请求ID = generateRequestId()
    const 超时 = 选项?.timeout || standardActionDef[动作 as keyof typeof standardActionDef]?.默认超时 || 10000
    const 结果 = registerPendingRequest(请求ID, 超时, () => ({
      success: false, error: { code: 'ERR_TIMEOUT', message: '请求超时' }
    }))
    emitter.emit('app:request', { targetAppId: 目标appId, action: 动作, params: 参数 || {}, requestId: 请求ID } as never)
    return 结果
  }

  async function requestData(
    目标appId: appId, T: string, 条件?: Record<string, unknown>, 选项?: CommandOptions
  ): Promise<CrossAppActionResponse> {
    return sendCommand(目标appId, `data:${T}`, 条件, 选项)
  }

  function subscribeEvent(事件名: string, 处理器: (载荷: unknown) => void): () => void {
    emitter.on(事件名 as never, 处理器 as never)
    return () => { emitter.off(事件名 as never, 处理器 as never) }
  }

  function unsubscribeEvent(事件名: string, 处理器?: (载荷: unknown) => void): void {
    if (处理器) {
      emitter.off(事件名 as never, 处理器 as never)
    }
  }

  function broadcastEvent(事件名: string, 载荷?: unknown): void {
    emitter.emit(事件名 as never, 载荷 as never)
  }

  function notifyUser(NotificationPayload: NotificationPayload): void {
    ElMessage({
      type: NotificationPayload.type || 'info',
      message: NotificationPayload.message,
      duration: NotificationPayload.duration || 3000,
    })
    if (NotificationPayload.targetApp) {
      emitter.emit('app:notification' as never, NotificationPayload as never)
    }
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
    注册数据处理器: (声明: DataHandlerDeclaration) => {
      registerActionHandler({ appKey: 声明.appKey, action: `data:${声明.dataType}`, handler: async (params, metadata) => {
        const 结果 = await 声明.handler(params, metadata)
        return { success: true, data: 结果.data }
      }})
    },
    unregisterAppHandlers,
     routeRequest: (appId: appId, 动作: string, 参数: Record<string, unknown>) =>
       routeRequest(appId, 动作, 参数, { sourceAppId: '', sourceWindowId: '', requestId: generateRequestId() }),
     getRegisteredAppIds,
     getRegisteredActions,
   }
}
