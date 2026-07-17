/**
 * Workspace Runtime 共享原语（WP5/WP6 骨架）。
 *
 * 四种布局：Document / Conversation / Catalog / Media。
 * 本轮只落类型与 chrome 壳，不翻转现有 Viewer 实现。
 */

export type WorkspaceKind =
  | 'DocumentWorkspace'
  | 'ConversationWorkspace'
  | 'CatalogWorkspace'
  | 'MediaWorkspace'

export interface DocumentSessionV1 {
  sessionId: string
  windowId?: string
  productId: string
  packageId?: number | null
  versionId?: number | null
  fileId?: number | null
  title?: string
  contentType?: string
  format?: string
  adapterId?: string
  requestedMode?: 'view' | 'edit'
  grantedMode?: 'view' | 'edit'
  lifecycle?: string
  dirty?: boolean
  expectedVersionId?: number | null
  lockToken?: string | null
  viewState?: Record<string, unknown>
}

export interface ProductWindowSessionV2 {
  windowId: string
  productId: string
  instanceKey?: string
  geometry?: { x?: number; y?: number; width?: number; height?: number }
  windowState?: string
  zOrder?: number
  active?: boolean
  tabOrder?: string[]
  activeDocumentSessionId?: string | null
  productState?: Record<string, unknown>
  restoreState?: Record<string, unknown>
  revision?: number
}

export function createEmptyDocumentSession(
  productId: string,
  partial: Partial<DocumentSessionV1> = {},
): DocumentSessionV1 {
  return {
    sessionId: `ds_${Date.now().toString(36)}`,
    productId,
    requestedMode: 'view',
    grantedMode: 'view',
    lifecycle: 'open',
    dirty: false,
    ...partial,
  }
}
