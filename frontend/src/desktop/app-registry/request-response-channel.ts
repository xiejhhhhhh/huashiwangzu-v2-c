import emitter from '@/desktop/events'
import type { CrossAppActionResponse } from './types-app-handle-v2'
import { routeRequest } from './action-registry'

const pendingRequests = new Map<string, {
  resolve: (value: CrossAppActionResponse) => void
  reject: (reason: unknown) => void
  timer: ReturnType<typeof setTimeout>
}>()

let requestIdCounter = 0

export function generateRequestId(): string {
  requestIdCounter += 1
  return `req_${Date.now()}_${requestIdCounter}`
}

emitter.on('app:response', (data: unknown) => {
  const response = data as CrossAppActionResponse & { requestId?: string }
  if (!response.requestId) return
  const id = response.requestId
  const pending = pendingRequests.get(id)
  if (pending) {
    clearTimeout(pending.timer)
    pendingRequests.delete(id)
    pending.resolve(response)
  }
})

emitter.on('app:request', async (data: unknown) => {
  const request = data as { targetAppId: string; action: string; params: Record<string, unknown>; requestId: string; sourceAppId?: string; sourceWindowId?: string }
  if (!request.requestId) return
  const result = await routeRequest(
    request.targetAppId,
    request.action,
    request.params,
    { sourceAppId: request.sourceAppId || '', sourceWindowId: request.sourceWindowId || '', requestId: request.requestId }
  )
  emitter.emit('app:response', { ...result, requestId: request.requestId } as never)
})

export function registerPendingRequest(
  requestId: string,
  timeout: number,
  timeoutCallback: () => CrossAppActionResponse
): Promise<CrossAppActionResponse> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingRequests.delete(requestId)
      resolve(timeoutCallback())
    }, timeout)
    pendingRequests.set(requestId, { resolve, reject, timer })
  })
}

export function cancelPendingRequest(requestId: string): void {
  const pending = pendingRequests.get(requestId)
  if (pending) {
    clearTimeout(pending.timer)
    pendingRequests.delete(requestId)
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
