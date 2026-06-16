import emitter from '@/desktop/events'
import type { CrossAppActionResponse } from './types-app-handle-v2'
import { routeRequest } from './action-registry'

const pendingRequests = new Map<string, {
  resolve: (value: CrossAppActionResponse) => void
  reject: (reason: unknown) => void
  timer: ReturnType<typeof setTimeout>
}>()

let 请求ID计数器 = 0

export function generateRequestId(): string {
  请求ID计数器 += 1
  return `req_${Date.now()}_${请求ID计数器}`
}

emitter.on('app:response', (数据: unknown) => {
  const 响应 = 数据 as CrossAppActionResponse & { requestId?: string }
  if (!响应.requestId && !(响应 as any).requestId) return
  const id = 响应.requestId || (响应 as any).requestId
  const pending = pendingRequests.get(id)
  if (pending) {
    clearTimeout(pending.timer)
    pendingRequests.delete(id)
    pending.resolve(响应)
  }
})

emitter.on('app:request', async (数据: unknown) => {
  const 请求 = 数据 as { targetAppId: string; action: string; params: Record<string, unknown>; requestId: string; sourceAppId?: string; sourceWindowId?: string }
  if (!请求.requestId) return
  const 结果 = await routeRequest(
    请求.targetAppId,
    请求.action,
    请求.params,
    { sourceAppId: 请求.sourceAppId || '', sourceWindowId: 请求.sourceWindowId || '', requestId: 请求.requestId }
  )
  emitter.emit('app:response', { ...结果, requestId: 请求.requestId } as never)
})

export function registerPendingRequest(
  请求ID: string,
  超时: number,
  超时回调: () => CrossAppActionResponse
): Promise<CrossAppActionResponse> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingRequests.delete(请求ID)
      resolve(超时回调())
    }, 超时)
    pendingRequests.set(请求ID, { resolve, reject, timer })
  })
}

export function cancelPendingRequest(请求ID: string): void {
  const pending = pendingRequests.get(请求ID)
  if (pending) {
    clearTimeout(pending.timer)
    pendingRequests.delete(请求ID)
    pending.resolve({ success: false, error: { code: 'ERR_TIMEOUT', message: '请求已取消' } })
  }
}

export function clearAllRequests(): void {
  pendingRequests.forEach((pending) => {
    clearTimeout(pending.timer)
    pending.resolve({ success: false, error: { code: 'ERR_TIMEOUT', message: '系统重置' } })
  })
  pendingRequests.clear()
}
