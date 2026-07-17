/**
 * Product Runtime 正式前端入口。
 *
 * - Catalog：只消费 /api/desktop/products
 * - Open：只消费 Content Open Resolver
 */
import { fetchDesktopProducts, type DesktopProductItem, type ProductCatalogResponse } from '@/shared/api/products'
import { openContent, type OpenContentIntent, type OpenContentResolution } from '@/shared/api/content-runtime'
import { productKeyMap } from './product-key-map.generated'

let cachedCatalog: ProductCatalogResponse | null = null

export async function loadProductCatalog(force = false): Promise<ProductCatalogResponse> {
  if (!force && cachedCatalog) return cachedCatalog
  cachedCatalog = await fetchDesktopProducts()
  return cachedCatalog
}

export function getCachedProduct(productId: string): DesktopProductItem | undefined {
  return cachedCatalog?.items.find((p) => p.productId === productId)
}

export function getBuildTimeProduct(productId: string) {
  return productKeyMap[productId]
}

/**
 * 打开内容：前端只提交 Intent，打开器结论完全由服务端 Resolver 给出。
 */
export async function resolveAndOpenContent(intent: OpenContentIntent): Promise<OpenContentResolution> {
  return openContent({
    resolverVersion: 'v1',
    activation: 'reuse-tab',
    requestedMode: 'view',
    ...intent,
  })
}

/** 正式文件打开解析 */
export async function resolveFileOpen(fileId: number, mode: 'view' | 'edit' = 'view') {
  return resolveAndOpenContent({
    source: { fileId },
    requestedMode: mode,
  })
}

export type { DesktopProductItem, ProductCatalogResponse, OpenContentIntent, OpenContentResolution }
