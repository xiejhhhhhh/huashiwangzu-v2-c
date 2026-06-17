import api, { API_BASE_URL } from './index'
import type { ApiResponse, FolderEntry, FileEntry, RecycleBinEntry, FileDetail } from './types'
export type { FileOpenPayload as FilePreviewPayload } from '@/desktop/window-manager/window-types'
import type { DesktopPersistentState } from '@/desktop/window-manager/desktop-state-store'

type FileItemType = 'file' | 'folder'

interface BackendFileListItem {
  id: number
  name: string
  extension?: string | null
  size: number
  parent_id?: number | null
  created_at?: string | null
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
    storage_path: item.storage_path ?? null,
    is_folder: item.is_folder,
    parent_folder_id: item.parent_id ?? null,
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

function toDesktopPersistentState(response: BackendDesktopStateResponse): DesktopPersistentState {
  const payload = response.state_json || {}
  return {
    version: payload.version ?? payload.版本 ?? response.version ?? 1,
    windows: Array.isArray(payload.windows) ? payload.windows : Array.isArray(payload.窗口) ? payload.窗口 : [],
    appState: payload.appState ?? payload.应用状态 ?? {},
  }
}

function toFileItemType(itemType: FileItemType): 'file' | 'folder' {
  return itemType
}

export function readDesktopStateRequest() {
  return api.get<unknown, ApiResponse<BackendDesktopStateResponse>>('/desktop/state')
    .then((response): ApiResponse<DesktopPersistentState> => ({
      ...response,
      data: response.data ? toDesktopPersistentState(response.data) : null,
    }))
}

export function saveDesktopStateRequest(state: DesktopPersistentState) {
  return api.post<unknown, ApiResponse<BackendDesktopStateResponse>>('/desktop/state', { state_json: state })
    .then((response): ApiResponse<DesktopPersistentState> => ({
      ...response,
      data: response.data ? toDesktopPersistentState(response.data) : null,
    }))
}

export function fetchFolderTree() {
  return api.get<unknown, ApiResponse<FolderEntry[]>>('/files/tree')
}

export function fetchFileList(folderId: number, page = 1, pageSize = 50) {
  return api.get<unknown, ApiResponse<BackendFileListResponse>>('/files/list', {
    params: { folder_id: folderId, page, page_size: pageSize },
  }).then((response): ApiResponse<FileListPageResponse> => ({
    ...response,
    data: response.data ? toFileListPage(response.data) : null,
  }))
}

export function createFolderRequest(name: string, parentFolderId?: number | null) {
  return api.post<unknown, ApiResponse<FolderEntry>>('/files/folder', { name, parent_id: parentFolderId })
}

export function renameEntryRequest(itemType: FileItemType, id: number, newName: string) {
  return api.post<unknown, ApiResponse<Record<string, unknown>>>('/files/rename', { type: toFileItemType(itemType), id, new_name: newName })
}

export function moveEntryRequest(itemType: FileItemType, id: number, targetFolderId?: number | null) {
  return api.post<unknown, ApiResponse<Record<string, unknown>>>('/files/move', { type: toFileItemType(itemType), id, target_folder_id: targetFolderId })
}

export function copyEntryRequest(itemType: FileItemType, id: number, targetFolderId?: number | null) {
  return api.post<unknown, ApiResponse<Record<string, unknown>>>('/files/copy', { type: toFileItemType(itemType), id, target_folder_id: targetFolderId })
}

export function moveToRecycleBinRequest(itemType: FileItemType, id: number) {
  return api.post<unknown, ApiResponse<Record<string, unknown>>>('/files/delete', { type: toFileItemType(itemType), id })
}

export function downloadFileRequest(fileId: number) {
  window.open(`${API_BASE_URL}/files/download/${fileId}`, '_blank')
}

interface CreateFileResponse {
  id: number
  name: string
  extension: string
  size: number
  mime_type: string
  deduplicated: boolean
}

export function createFileRequest(name: string, extension: string, folderId?: number | null) {
  return api.post<unknown, ApiResponse<CreateFileResponse>>('/files/create-file', {
    name, extension, folder_id: folderId || null,
  })
}

export function uploadFileRequest(file: File, folderId?: number, onProgress?: (pct: number) => void) {
  const formData = new FormData()
  formData.append('file', file)
  if (folderId !== undefined) {
    formData.append('folder_id', String(folderId))
  }
  return api.post<unknown, ApiResponse<UploadFileResponse>>('/files/upload', formData, {
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

export function fetchRecycleBinList() {
  return api.get<unknown, ApiResponse<RecycleBinEntry[]>>('/recycle/list')
}

export function restoreRecycleBinEntry(itemType: FileItemType, id: number) {
  return api.post<unknown, ApiResponse<Record<string, unknown>>>('/recycle/restore', { item_type: itemType, id })
}

export function permanentlyDeleteEntry(itemType: FileItemType, id: number) {
  return api.post<unknown, ApiResponse<Record<string, unknown>>>('/recycle/delete-permanently', { item_type: itemType, id })
}

export function emptyRecycleBinRequest() {
  return api.post<unknown, ApiResponse<{ message: string }>>('/recycle/empty')
}

export interface FileSearchPageResponse {
  items: FileEntry[]
  total: number
  page: number
  page_size: number
}

export function searchFilesRequest(keyword: string, extension?: string, page = 1, pageSize = 50) {
  return api.get<unknown, ApiResponse<BackendFileListResponse>>('/files/search', {
    params: { keyword, extension, page, page_size: pageSize }
  }).then((response): ApiResponse<FileSearchPageResponse> => ({
    ...response,
    data: response.data ? toFileListPage(response.data) : null,
  }))
}

export function fetchFileDetail(fileId: number) {
  return api.get<unknown, ApiResponse<FileDetail>>(`/files/detail/${fileId}`)
}

export function fetchFilePreview(fileId: number) {
  return api.get<unknown, ApiResponse<Record<string, unknown>>>(`/files/preview/${fileId}`)
}

export function getFilePreviewUrl(fileId: number): string {
  return `${API_BASE_URL}/files/preview/${fileId}`
}
