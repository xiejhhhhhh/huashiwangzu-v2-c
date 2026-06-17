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

export const auditLevels = {
  none: 'none',
  low: 'low',
  medium: 'medium',
  high: 'high',
} as const

export type AuditLevel = (typeof auditLevels)[keyof typeof auditLevels]

export const standardActionDef = {
  'file:open': {
    name: 'openFile',
    paramSchema: { fileId: 'number', format: 'string?' },
    defaultTimeout: 15000,
    auditLevel: 'low' as AuditLevel,
  },
  'settings:open': {
    name: 'openSettings',
    paramSchema: { page: 'string?', highlightedField: 'string?' },
    defaultTimeout: 10000,
    auditLevel: 'none' as AuditLevel,
  },
  'feedback:open': {
    name: 'openFeedback',
    paramSchema: { presetType: 'string?', presetDescription: 'string?' },
    defaultTimeout: 10000,
    auditLevel: 'none' as AuditLevel,
  },
} as const

export type StandardAction = keyof typeof standardActionDef

export interface AuditLogEntry {
  action: string
  params: Record<string, unknown>
  sourceApp: appId
  targetApp?: appId
  sourceWindowId?: windowId
  userId?: number
}
