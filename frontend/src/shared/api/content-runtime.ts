import api from './index'

export interface OpenContentIntent {
  resolverVersion?: string
  requestId?: string
  source: {
    fileId?: number | null
    packageId?: number | null
    versionId?: number | null
    deepLink?: string | null
  }
  requestedMode?: 'view' | 'edit'
  preferredProductId?: string | null
  activation?: 'reuse-tab' | 'new-tab' | 'new-window'
  expectedVersionId?: number | null
  lockToken?: string | null
  origin?: Record<string, unknown>
}

export interface OpenContentResolution {
  resolutionId: string
  requestId: string
  outcome: string
  productId?: string | null
  adapterId?: string | null
  grantedMode: string
  readonlyReason?: string | null
  product?: Record<string, unknown>
  file?: Record<string, unknown> | null
  package?: Record<string, unknown> | null
  version?: Record<string, unknown> | null
  session?: Record<string, unknown> | null
  catalogRevision?: string
  title?: string
  format?: string
}

export function openContent(intent: OpenContentIntent) {
  return api.post<unknown, OpenContentResolution>('/content/open', intent)
}

export function createContentDraft(payload: {
  productId?: string
  contentType?: string
  extension?: string
  title?: string
  adapterId?: string
}) {
  return api.post<unknown, Record<string, unknown>>('/content/drafts', payload)
}

export function hydrateContentPackage(
  packageId: number,
  params: Record<string, string | number | undefined> = {},
) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return api.get<unknown, Record<string, unknown>>(`/content/packages/${packageId}/hydrate${suffix}`)
}

export function saveContentPackage(
  packageId: number,
  payload: {
    expectedVersionId?: number | null
    lockToken?: string | null
    content?: Record<string, unknown> | null
    summary?: string
    autosave?: boolean
  },
) {
  return api.post<unknown, Record<string, unknown>>(`/content/packages/${packageId}/save`, payload)
}

export function acquireContentLock(packageId: number, payload: { baseVersionId?: number; ttlSeconds?: number } = {}) {
  return api.post<unknown, Record<string, unknown>>(`/content/packages/${packageId}/locks`, payload)
}

export function renewContentLock(packageId: number, token: string, ttlSeconds = 300) {
  return api.post<unknown, Record<string, unknown>>(`/content/packages/${packageId}/locks/renew`, {
    token,
    ttlSeconds,
  })
}

export function releaseContentLock(packageId: number, token: string) {
  return api.delete<unknown, Record<string, unknown>>(`/content/packages/${packageId}/locks/${token}`)
}

export function fetchOfficeHome() {
  return api.get<unknown, Record<string, unknown>>('/office/home')
}

export function exportContentPackage(packageId: number, format?: string) {
  return api.post<unknown, Record<string, unknown>>(`/content/packages/${packageId}/export`, { format: format || null })
}

export function publishContentPackage(
  packageId: number,
  payload: { targetFileId?: number | null; conflictPolicy?: string } = {},
) {
  return api.post<unknown, Record<string, unknown>>(`/content/packages/${packageId}/publish`, {
    targetFileId: payload.targetFileId ?? null,
    conflictPolicy: payload.conflictPolicy || 'create_version',
  })
}

