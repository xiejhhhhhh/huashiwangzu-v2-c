import api, { API_BASE_URL } from './index'
import type { FolderEntry, FileEntry, RecycleBinEntry, FileDetail } from './types'
export type { FileOpenPayload as FilePreviewPayload } from '@/desktop/window-manager/window-types'
import type { DesktopPersistentState } from '@/desktop/window-manager/desktop-state-store'

type FileItemType = 'file' | 'folder'

interface BackendFileListItem {
  id: number
  name: string
  extension?: string | null
  size: number
  parent_id?: number | null
  folder_id?: number | null
  created_at?: string | null
  updated_at?: string | null
  is_folder: boolean
  mime_type?: string | null
  storage_path?: string | null
}

interface BackendFileListResponse {
  items: BackendFileListItem[]
  total: number
  page: number
  page_size: number
}

interface BackendDesktopStateResponse {
  user_id: number
  state_json: Partial<DesktopPersistentState> & {
    版本?: number
    窗口?: DesktopPersistentState['windows']
    应用状态?: DesktopPersistentState['appState']
    图标位置?: DesktopPersistentState['iconPositions']
  }
  version: number
}

interface UploadFileResponse {
  exists: boolean
  deduplicated?: boolean
  id: number
  name: string
  extension: string
  size?: number | null
  mime_type?: string | null
}

export interface FileListPageResponse {
  items: FileEntry[]
  total: number
  page: number
  page_size: number
}

function toFileEntry(item: BackendFileListItem): FileEntry {
  return {
    id: item.id,
    file_name: item.name,
    format: item.extension ?? null,
    file_size: item.size,
    created_at: item.created_at ?? '',
    updated_at: item.updated_at ?? item.created_at ?? null,
    storage_path: item.storage_path ?? null,
    is_folder: item.is_folder,
    parent_folder_id: item.parent_id ?? item.folder_id ?? null,
  }
}

function toFileListPage(data: BackendFileListResponse): FileListPageResponse {
  return {
    items: data.items.map(toFileEntry),
    total: data.total,
    page: data.page,
    page_size: data.page_size,
  }
}

export interface DesktopStateEnvelope {
  state: DesktopPersistentState
  /** framework_desktop_states.version，CAS 用 */
  serverVersion: number
}

function toDesktopPersistentState(response: BackendDesktopStateResponse): DesktopStateEnvelope {
  const payload = response.state_json || {}
  const serverVersion = Number(response.version ?? 1) || 1
  return {
    serverVersion,
    state: {
      // 内容版本与服务端 CAS 版本解耦：state.version 只服务前端快照，CAS 用 serverVersion
      version: payload.version ?? payload.版本 ?? serverVersion,
      windows: Array.isArray(payload.windows) ? payload.windows : Array.isArray(payload.窗口) ? payload.窗口 : [],
      appState: payload.appState ?? payload.应用状态 ?? {},
      iconPositions: payload.iconPositions ?? payload.图标位置 ?? {},
    },
  }
}

export async function readDesktopStateRequest(): Promise<DesktopStateEnvelope> {
  const data = await api.get<unknown, BackendDesktopStateResponse>('/desktop/state')
  return toDesktopPersistentState(data)
}

export async function saveDesktopStateRequest(
  state: DesktopPersistentState,
  expectedVersion?: number | null,
): Promise<DesktopStateEnvelope> {
  // WP6 CAS：带 expected_version，冲突由上层决定是否重载
  // state_json 不回传 version 字段给 CAS，避免与服务端 version 混淆
  const { version: _ignored, ...stateJson } = state as DesktopPersistentState & { version?: number }
  const body: Record<string, unknown> = { state_json: stateJson }
  if (expectedVersion !== undefined && expectedVersion !== null) {
    body.expected_version = expectedVersion
  }
  const data = await api.post<unknown, BackendDesktopStateResponse>('/desktop/state', body)
  return toDesktopPersistentState(data)
}

export async function fetchFolderTree(): Promise<FolderEntry[]> {
  return await api.get<unknown, FolderEntry[]>('/files/tree')
}

export async function fetchFileList(folderId: number, page = 1, pageSize = 50): Promise<FileListPageResponse> {
  const data = await api.get<unknown, BackendFileListResponse>('/files/list', {
    params: { folder_id: folderId, page, page_size: pageSize },
  })
  return toFileListPage(data)
}

export async function createFolderRequest(name: string, parentFolderId?: number | null): Promise<FolderEntry> {
  return await api.post<unknown, FolderEntry>('/files/folder', { name, parent_id: parentFolderId })
}

export type FinderLocationKey = 'desktop' | 'documents' | 'downloads'

export interface FinderLocation {
  key: FinderLocationKey | string
  id: number
  name: string
}

export async function fetchFinderLocations(): Promise<Record<string, FinderLocation>> {
  return await api.get<unknown, Record<string, FinderLocation>>('/files/locations')
}

export type FileTagItemType = 'file' | 'folder'

export async function fetchFileTagsMap(): Promise<Record<string, string[]>> {
  return await api.get<unknown, Record<string, string[]>>('/files/tags')
}

export async function setFileItemTagsRequest(
  itemType: FileTagItemType,
  itemId: number,
  tags: string[],
): Promise<string[]> {
  const data = await api.put<unknown, { tags?: string[] }>('/files/tags', {
    item_type: itemType,
    item_id: itemId,
    tags,
  })
  return Array.isArray(data?.tags) ? data.tags : tags
}

export async function toggleFileItemTagRequest(
  itemType: FileTagItemType,
  itemId: number,
  tag: string,
): Promise<string[]> {
  const data = await api.post<unknown, { tags?: string[] }>('/files/tags/toggle', {
    item_type: itemType,
    item_id: itemId,
    tag,
  })
  return Array.isArray(data?.tags) ? data.tags : []
}

export async function clearFileItemTagsRequest(
  itemType: FileTagItemType,
  itemId: number,
): Promise<void> {
  await setFileItemTagsRequest(itemType, itemId, [])
}

export async function renameEntryRequest(itemType: FileItemType, id: number, newName: string): Promise<Record<string, unknown>> {
  return await api.post<unknown, Record<string, unknown>>('/files/rename', { type: itemType, id, new_name: newName })
}

export async function moveEntryRequest(itemType: FileItemType, id: number, targetFolderId?: number | null): Promise<Record<string, unknown>> {
  return await api.post<unknown, Record<string, unknown>>('/files/move', { type: itemType, id, target_folder_id: targetFolderId })
}

export async function copyEntryRequest(itemType: FileItemType, id: number, targetFolderId?: number | null): Promise<Record<string, unknown>> {
  return await api.post<unknown, Record<string, unknown>>('/files/copy', { type: itemType, id, target_folder_id: targetFolderId })
}

export async function moveToRecycleBinRequest(itemType: FileItemType, id: number): Promise<Record<string, unknown>> {
  return await api.post<unknown, Record<string, unknown>>('/files/delete', { type: itemType, id })
}

export interface BatchFileItem {
  id: number
  item_type: FileItemType
}

export async function batchDeleteRequest(items: BatchFileItem[]): Promise<{
  success_count: number
  failed_count: number
  items: Array<{ id: number; type: string; success: boolean; error?: string | null }>
}> {
  return await api.post<unknown, {
    success_count: number
    failed_count: number
    items: Array<{ id: number; type: string; success: boolean; error?: string | null }>
  }>('/files/batch-delete', { items })
}

export async function batchMoveRequest(
  items: BatchFileItem[],
  targetFolderId?: number | null,
): Promise<{
  success_count: number
  failed_count: number
  items: Array<{ id: number; type: string; success: boolean; error?: string | null }>
}> {
  return await api.post<unknown, {
    success_count: number
    failed_count: number
    items: Array<{ id: number; type: string; success: boolean; error?: string | null }>
  }>('/files/batch-move', {
    items,
    target_folder_id: targetFolderId ?? null,
  })
}

export async function batchCopyRequest(
  items: BatchFileItem[],
  targetFolderId?: number | null,
): Promise<{
  success_count: number
  failed_count: number
  items: Array<{ id: number; type: string; success: boolean; error?: string | null; new_id?: number | null }>
}> {
  return await api.post<unknown, {
    success_count: number
    failed_count: number
    items: Array<{ id: number; type: string; success: boolean; error?: string | null; new_id?: number | null }>
  }>('/files/batch-copy', {
    items,
    target_folder_id: targetFolderId ?? null,
  })
}

export async function compressEntriesRequest(items: BatchFileItem[]): Promise<{ blob: Blob; filename: string }> {
  const blob = await api.post<unknown, Blob>('/files/compress', { items }, {
    responseType: 'blob',
  })
  if (!(blob instanceof Blob)) {
    throw new Error('compress response is not a blob')
  }
  // response interceptor strips headers for blob; name is best-effort client default
  const filename = items.length === 1 ? '归档.zip' : `归档-${items.length}项.zip`
  return { blob, filename }
}

export async function downloadFileRequest(fileId: number, filename?: string) {
  const response = await api.get<unknown, Blob>(`/files/download/${fileId}`, { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(response)
  const link = document.createElement('a')
  link.href = objectUrl
  if (filename) link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
}

interface CreateFileResponse {
  id: number
  name: string
  extension: string
  size: number
  mime_type: string
  deduplicated: boolean
}

export async function createFileRequest(name: string, extension: string, folderId?: number | null): Promise<CreateFileResponse> {
  return await api.post<unknown, CreateFileResponse>('/files/create-file', {
    name, extension, folder_id: folderId || null,
  })
}

export async function uploadFileRequest(file: File, folderId?: number, onProgress?: (pct: number) => void): Promise<UploadFileResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (folderId !== undefined) {
    formData.append('folder_id', String(folderId))
  }
  return await api.post<unknown, UploadFileResponse>('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
      ? (e) => {
          if (e.total) {
            onProgress(Math.round((e.loaded / e.total) * 100))
          }
        }
      : undefined,
  })
}

export async function fetchRecycleBinList(): Promise<RecycleBinEntry[]> {
  return await api.get<unknown, RecycleBinEntry[]>('/recycle/list')
}

export async function restoreRecycleBinEntry(itemType: FileItemType, id: number): Promise<Record<string, unknown>> {
  return await api.post<unknown, Record<string, unknown>>('/recycle/restore', { item_type: itemType, id })
}

export async function permanentlyDeleteEntry(itemType: FileItemType, id: number): Promise<Record<string, unknown>> {
  return await api.post<unknown, Record<string, unknown>>('/recycle/delete-permanently', { item_type: itemType, id })
}

export async function emptyRecycleBinRequest(): Promise<{ message: string }> {
  return await api.post<unknown, { message: string }>('/recycle/empty')
}

export interface FileSearchPageResponse {
  items: FileEntry[]
  total: number
  page: number
  page_size: number
}

export async function searchFilesRequest(
  keyword: string,
  extension?: string,
  page = 1,
  pageSize = 50,
  opts?: { folderId?: number | null; recursive?: boolean },
): Promise<FileSearchPageResponse> {
  const data = await api.get<unknown, BackendFileListResponse>('/files/search', {
    params: {
      keyword,
      extension,
      page,
      page_size: pageSize,
      folder_id: opts?.folderId == null ? undefined : opts.folderId,
      recursive: opts?.recursive ?? true,
    },
  })
  return toFileListPage(data)
}

export async function fetchFileDetail(fileId: number): Promise<FileDetail> {
  return await api.get<unknown, FileDetail>(`/files/detail/${fileId}`)
}


export async function fetchDownloadBlob(fileId: number, variant?: 'original' | 'standard-image'): Promise<Blob> {
  const suffix = variant ? `/${variant}` : ''
  return await api.get<unknown, Blob>(`/files/download/${fileId}${suffix}`, { responseType: 'blob' })
}

export async function fetchBlobByApiPath(path: string): Promise<Blob> {
  const cleaned = path
    .replace(/^https?:\/\/[^/]+/i, '')
    .replace(/^\/api(?=\/)/, '')
  const url = cleaned.startsWith('/') ? cleaned : `/${cleaned}`
  return await api.get<unknown, Blob>(url, { responseType: 'blob' })
}

export async function fetchFilePreview(fileId: number): Promise<Record<string, unknown>> {
  return await api.get<unknown, Record<string, unknown>>(`/files/preview/${fileId}`)
}

export function getFilePreviewUrl(fileId: number): string {
  return `${API_BASE_URL}/files/preview/${fileId}`
}
