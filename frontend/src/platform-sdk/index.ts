/**
 * Platform SDK thin entry (WP6).
 *
 * Legacy modules runtime copies may remain during compatibility period.
 * New code should re-export from here instead of duplicating API bridges.
 */
export { openContent, createContentDraft, hydrateContentPackage, saveContentPackage, fetchOfficeHome, exportContentPackage, publishContentPackage } from '@/shared/api/content-runtime'
export { fetchDesktopProducts, getDesktopProduct } from '@/shared/api/products'
export { resolveAndOpenContent, loadProductCatalog, resolveFileOpen } from '@/product-runtime'
