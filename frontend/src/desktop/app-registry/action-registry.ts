import type { appId, CrossAppActionResponse, ActionHandlerDeclaration } from './types-app-handle-v2'

const 处理器注册表 = new Map<appId, Map<string, ActionHandlerDeclaration['handler']>>()

export function registerActionHandler(声明: ActionHandlerDeclaration): void {
  if (!处理器注册表.has(声明.appKey)) {
    处理器注册表.set(声明.appKey, new Map())
  }
  处理器注册表.get(声明.appKey)!.set(声明.action, 声明.handler)
}

export function unregisterAppHandlers(应用标识: appId): void {
  处理器注册表.delete(应用标识)
}

export function unregisterActionHandler(应用标识: appId, 动作: string): void {
  const 应用处理器 = 处理器注册表.get(应用标识)
  if (应用处理器) {
    应用处理器.delete(动作)
    if (应用处理器.size === 0) {
      处理器注册表.delete(应用标识)
    }
  }
}

export function getRegisteredAppIds(): appId[] {
  return Array.from(处理器注册表.keys())
}

export function getRegisteredActions(应用标识: appId): string[] {
  const 应用处理器 = 处理器注册表.get(应用标识)
  return 应用处理器 ? Array.from(应用处理器.keys()) : []
}

export async function routeRequest(
  目标appId: appId,
  动作: string,
  参数: Record<string, unknown>,
  metadata: { sourceAppId: appId; sourceWindowId: string; requestId: string }
): Promise<CrossAppActionResponse> {
  const 应用处理器 = 处理器注册表.get(目标appId)
  if (!应用处理器) {
    return { success: false, error: { code: 'ERR_HANDLER_NOT_REGISTERED', message: `应用 ${目标appId} 未注册任何处理器` } }
  }
  const 处理器 = 应用处理器.get(动作)
  if (!处理器) {
    return { success: false, error: { code: 'ERR_ACTION_NOT_PUBLIC', message: `应用 ${目标appId} 未公开动作 ${动作}` } }
  }
  return await 处理器(参数, metadata)
}

export function isHandlerRegistered(目标appId: appId, 动作: string): boolean {
  const 应用处理器 = 处理器注册表.get(目标appId)
  return 应用处理器 ? 应用处理器.has(动作) : false
}
