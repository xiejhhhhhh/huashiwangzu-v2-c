import api, { API_BASE_URL } from './index'
import type { 统一响应, 文件夹条目, FileEntry, 回收站条目, 文件详情数据 } from './types'
export type { FileOpenPayload as FilePreviewPayload } from '@/desktop/window-manager/window-types'
import type { DesktopPersistentState } from '@/desktop/window-manager/desktop-state-store'

export function 读取桌面状态请求() {
  return api.get<unknown, 统一响应<DesktopPersistentState>>('/desktop/state')
}

export function 保存桌面状态请求(状态: DesktopPersistentState) {
  return api.post<unknown, 统一响应<DesktopPersistentState>>('/desktop/state', 状态)
}

export function 获取文件夹树请求() {
  return api.get<unknown, 统一响应<文件夹条目[]>>('/files/tree')
}

export function 获取文件列表请求(文件夹id: number, 页码 = 1, 每页数量 = 50) {
  return api.get<unknown, 统一响应<any>>('/files/list', { params: { folder_id: 文件夹id, page: 页码, page_size: 每页数量 } })
}

export function 新建文件夹请求(名称: string, 父文件夹id?: number | null) {
  return api.post<unknown, 统一响应<文件夹条目>>('/files/folder', { name: 名称, parent_id: 父文件夹id })
}

export function 重命名请求(类型: '文件' | '文件夹', id: number, 新名称: string) {
  return api.post<unknown, 统一响应<any>>('/files/rename', { type: 转条目类型(类型), id, new_name: 新名称 })
}

export function 移动条目请求(类型: '文件' | '文件夹', id: number, 目标文件夹id?: number | null) {
  return api.post<unknown, 统一响应<any>>('/files/move', { type: 转条目类型(类型), id, target_folder_id: 目标文件夹id })
}

export function 复制条目请求(类型: '文件' | '文件夹', id: number, 目标文件夹id?: number | null) {
  return api.post<unknown, 统一响应<any>>('/files/copy', { type: 转条目类型(类型), id, target_folder_id: 目标文件夹id })
}

export function 移动到回收站请求(类型: '文件' | '文件夹', id: number) {
  return api.post<unknown, 统一响应<any>>('/files/delete', { type: 转条目类型(类型), id })
}

export function 下载文件请求(文件id: number) {
  window.open(`${API_BASE_URL}/files/download/${文件id}`, '_blank')
}

export function 上传文件请求(文件: File, 文件夹id?: number, onProgress?: (pct: number) => void) {
  const formData = new FormData()
  formData.append('file', 文件)
  if (文件夹id !== undefined) {
    formData.append('folder_id', String(文件夹id))
  }
  return api.post<unknown, 统一响应<{
    已存在: boolean
    文件id: number
    文件名: string
    格式: string
    文件大小: number
    分析支持?: boolean
    分析提示?: string
  }>>('/files/upload', formData, {
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

export function 回收站列表请求() {
  return api.get<unknown, 统一响应<回收站条目[]>>('/recycle/list')
}

export function 回收站还原请求(类型: '文件' | '文件夹', id: number) {
  return api.post<unknown, 统一响应<any>>('/recycle/restore', { item_type: 类型, id })
}

export function 彻底删除请求(类型: '文件' | '文件夹', id: number) {
  return api.post<unknown, 统一响应<any>>('/recycle/delete-permanently', { item_type: 类型, id })
}

export function 清空回收站请求() {
  return api.post<unknown, 统一响应<{ message: string }>>('/recycle/empty')
}

export interface FileSearchPageResponse {
  列表: FileEntry[]
  总数: number
  页码: number
  每页数量: number
}

export function 文件搜索请求(关键词: string, 格式?: string, 页码 = 1, 每页数量 = 50) {
  return api.get<unknown, 统一响应<FileSearchPageResponse>>('/files/search', {
    params: { keyword: 关键词, extension: 格式, page: 页码, page_size: 每页数量 }
  })
}

export function 文件详情请求(文件id: number) {
  return api.get<unknown, 统一响应<文件详情数据>>(`/files/detail/${文件id}`)
}

export function 获取文件预览请求(文件id: number) {
  return api.get<unknown, 统一响应<any>>(`/files/preview/${文件id}`)
}

export function 获取文件预览Url(文件id: number): string {
  return `${API_BASE_URL}/files/preview/${文件id}`
}

function 转条目类型(类型: '文件' | '文件夹'): 'file' | 'folder' {
  return 类型 === '文件' ? 'file' : 'folder'
}
