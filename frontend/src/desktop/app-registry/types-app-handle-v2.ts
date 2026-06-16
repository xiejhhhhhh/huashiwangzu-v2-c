export type appId = string
export type windowId = string
export type instanceId = string
export type documentId = number | string

export interface WindowHandle {
  windowId: windowId
  appId: appId
}

export interface MessageMeta {
  source: {
    appId: appId
    windowId: windowId
    instanceId?: instanceId
  }
  target: {
    appId: appId
    windowId?: windowId
  }
  requestId?: string
}

export interface CrossAppActionRequest {
  action: string
  params: Record<string, unknown>
  metadata?: {
    sourceAppId: appId
    sourceWindowId: windowId
    timestamp: number
  }
}

export interface CrossAppActionResponse {
  success: boolean
  data?: unknown
  handle?: WindowHandle
  error?: {
    code: string
    message: string
  }
}

export interface ActionHandlerDeclaration {
  appKey: appId
  action: string
  handler: (
    params: Record<string, unknown>,
    metadata: { sourceAppId: appId; sourceWindowId: windowId; requestId: string }
  ) => Promise<CrossAppActionResponse>
}

export interface DataHandlerDeclaration {
  appKey: appId
  dataType: string
  handler: (
    filter: Record<string, unknown>,
    metadata: { sourceAppId: appId; requestId: string }
  ) => Promise<{ data: unknown; metadata?: { total?: number } }>
}

export interface CommandOptions {
  timeout?: number
  newWindow?: boolean
}

export interface NotificationPayload {
  title: string
  message: string
  type?: 'info' | 'success' | 'warning' | 'error'
  targetApp?: appId
  duration?: number
}

export const errorCodes = {
  ERR_APP_NOT_FOUND: 'ERR_APP_NOT_FOUND',
  ERR_APP_DISABLED: 'ERR_APP_DISABLED',
  ERR_PERMISSION_DENIED: 'ERR_PERMISSION_DENIED',
  ERR_ACTION_NOT_PUBLIC: 'ERR_ACTION_NOT_PUBLIC',
  ERR_INVALID_PARAMS: 'ERR_INVALID_PARAMS',
  ERR_TIMEOUT: 'ERR_TIMEOUT',
  ERR_HANDLER_NOT_REGISTERED: 'ERR_HANDLER_NOT_REGISTERED',
  ERR_FORMAT_NOT_SUPPORTED: 'ERR_FORMAT_NOT_SUPPORTED',
} as const

export const AuditLevel = {
  none: 'none',
  low: 'low',
  medium: 'medium',
  high: 'high',
} as const

export type AuditLevel = (typeof AuditLevel)[keyof typeof AuditLevel]

export const standardActionDef = {
  'file:open': {
    名称: 'openFile',
    参数Schema: { 文件id: 'number', 格式: 'string?' },
    默认超时: 15000,
    AuditLevel: 'low' as AuditLevel,
  },
  'knowledge:node:open': {
    名称: '跳转知识节点',
    参数Schema: { 编目id: 'number', 定位锚点: 'string?' },
    默认超时: 10000,
    AuditLevel: 'none' as AuditLevel,
  },
  'agent:send': {
    名称: '发送给Agent',
    参数Schema: { 内容: 'string', 上下文: 'object?' },
    默认超时: 30000,
    AuditLevel: 'medium' as AuditLevel,
  },
  'settings:open': {
    名称: '打开设置页',
    参数Schema: { 页面: 'string?', 高亮字段: 'string?' },
    默认超时: 10000,
    AuditLevel: 'none' as AuditLevel,
  },
  'feedback:open': {
    名称: '打开反馈',
    参数Schema: { 预填类型: 'string?', 预填描述: 'string?' },
    默认超时: 10000,
    AuditLevel: 'none' as AuditLevel,
  },
} as const

export type StandardAction = keyof typeof standardActionDef

export interface AuditLogEntry {
  动作: string
  参数: Record<string, unknown>
  来源应用: appId
  目标应用?: appId
  来源窗口ID?: windowId
  userId?: number
}
