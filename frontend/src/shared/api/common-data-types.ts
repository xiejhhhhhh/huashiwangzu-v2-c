export interface FolderEntry {
  id: number
  name: string
  parent_folder_id: number | null
}
export interface FileParseResult {
  [key: string]: unknown
}

export interface NotificationItem {
  id: number
  title: string
  notification_type: string
  is_read: boolean
  published_at: string
  [key: string]: unknown
}

export interface SystemLogEntry {
  id: number
  level: string
  category: string
  message: string
  created_at: string
  [key: string]: unknown
}
export interface FileEntry {
  id: number
  file_name: string
  format: string | null
  file_size: number
  created_at: string
  storage_path: string | null
  is_folder?: boolean
  parent_folder_id?: number | null
}

export interface RecycleBinEntry {
  id: number
  origin_id: number
  name: string
  item_type: 'file' | 'folder'
  deleted_at: string
  format?: string | null
  size?: number | null
}

export interface FileDetail {
  id: number
  name: string
  extension: string
  size: number
  folder_id: number
  folder_name: string
  created_at: string
  updated_at: string
  storage_path: string
  deleted: boolean
  mime_type: string
  access_permission?: string
}

export interface LogEntry {
  id: number
  level: string
  category: string
  message: string
  created_at: string
}

export interface TaskItem {
  id: number
  task_type: string
  module_name: string
  status: string
  priority: number
  params: string | null
  result: string | null
  error_message: string | null
  retry_count: number
  max_retries: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  creator_id: number | null
}

export interface SystemConfig {
  project_name: string
  system_version: string
  login_page_title: string
  default_role: string
}

export interface RoleMatrixItem {
  role: string
  name: string
  user_management: boolean
  system_config: boolean
  role_matrix: boolean
}
