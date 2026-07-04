export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T | null
  error?: string | null
  errors?: Record<string, string> | { field: string; message: string }[] | null
}

export type { ApiErrorInfo } from './response-transform'

export interface LoginParams {
  username: string
  password: string
}

export interface UserInfo {
  id?: number
  username?: string
  display_name?: string
  displayName?: string
  email?: string
  role?: string
}

export interface MenuItem {
  name: string
  path: string
  icon: string
}

export interface PaginatedResult<T> {
  current_page: number
  data: T[]
  last_page: number
  per_page: number
  total: number
}

export interface SystemStatusEntry {
  status: boolean
  message: string
}

export interface SystemStatus {
  backend: SystemStatusEntry
  database: SystemStatusEntry
  worker: SystemStatusEntry
  modelService: SystemStatusEntry
  productionEntry: SystemStatusEntry
}

export type {
  FolderEntry, FileEntry, RecycleBinEntry, FileDetail,
  LogEntry, TaskItem,
  SystemConfig, RoleMatrixItem, FileParseResult,
  NotificationItem, SystemLogEntry,
} from './common-data-types'
