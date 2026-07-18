import api from './index'
import type { MacAppUiContract } from '@/desktop/app-kit'

export interface DesktopProductItem {
  productId: string
  version?: string
  displayName: string
  aliases?: string[]
  description?: string
  category?: string
  icon?: string
  iconSet?: Record<string, unknown>
  entryComponentKey: string
  workspaceKind?: string
  /** App UI Kit contract (mac-app-v1). Backend passthrough only. */
  uiContract?: MacAppUiContract | null
  visibility?: Record<string, unknown>
  fileAssociations?: Array<Record<string, unknown>>
  createDocumentTypes?: Array<Record<string, unknown>>
  windowPolicy?: Record<string, unknown>
  activationPolicy?: Record<string, unknown>
  deepLinks?: string[]
  commands?: string[]
  legacyAppKeys?: string[]
  enabled?: boolean
  sortOrder?: number
  defaultWidth?: number
  defaultHeight?: number
  singleton?: boolean
  allowMultiple?: boolean
  catalogRevision?: string
  manifestHash?: string
}

export interface ProductCatalogResponse {
  catalogRevision: string
  count: number
  items: DesktopProductItem[]
  kind: 'products'
}

export function fetchDesktopProducts() {
  return api.get<unknown, ProductCatalogResponse>('/desktop/products')
}

export function getDesktopProduct(productId: string) {
  return api.get<unknown, DesktopProductItem>(`/desktop/products/${productId}`)
}
