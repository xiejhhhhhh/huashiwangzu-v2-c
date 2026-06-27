import api from './index'
import type { SystemConfig, RoleMatrixItem } from './types'

interface BackendUser {
  id: number
  username: string
  display_name: string
  email: string | null
  role: string
  enabled: boolean
  last_login: string | null
  created_at: string
}

interface BackendUserSearchResponse {
  users: BackendUser[]
  total: number
  keyword: string
}

interface BackendRoleMatrixItem {
  role_key: string
  display_name: string
  permissions: {
    user_management?: boolean
    system_config?: boolean
    role_matrix?: boolean
  }
}

interface BackendRoleMatrixResponse {
  matrix: BackendRoleMatrixItem[]
}

export interface UserEntry {
  id: number
  username: string
  displayName: string
  email: string
  role: string
  status: number
  createdAt: string
  lastLogin: string
}

export interface UserListResponse {
  userList: UserEntry[]
  total: number
}

function toUserEntry(user: BackendUser): UserEntry {
  return {
    id: user.id,
    username: user.username,
    displayName: user.display_name,
    email: user.email ?? '',
    role: user.role,
    status: user.enabled ? 1 : 0,
    createdAt: user.created_at,
    lastLogin: user.last_login ?? '',
  }
}

function toRoleMatrixItem(item: BackendRoleMatrixItem): RoleMatrixItem {
  return {
    role: item.role_key,
    name: item.display_name,
    user_management: Boolean(item.permissions.user_management),
    system_config: Boolean(item.permissions.system_config),
    role_matrix: Boolean(item.permissions.role_matrix),
  }
}

function toRoleMatrixOutput(matrix: RoleMatrixItem[]): BackendRoleMatrixResponse {
  return {
    matrix: matrix.map(item => ({
      role_key: item.role,
      display_name: item.name,
      permissions: {
        user_management: item.user_management,
        system_config: item.system_config,
        role_matrix: item.role_matrix,
      },
    })),
  }
}

export async function fetchUserList(): Promise<UserListResponse> {
  const users = await api.get<unknown, BackendUser[]>('/users/')
  return { userList: users.map(toUserEntry), total: users.length }
}

export async function searchUsers(keyword: string): Promise<UserListResponse> {
  const data = await api.get<unknown, BackendUserSearchResponse>('/users/search', {
    params: { keyword },
  })
  return { userList: (data?.users ?? []).map(toUserEntry), total: data?.total ?? 0 }
}

export async function createUser(params: {
  username: string
  password: string
  displayName?: string
  email?: string
  role?: string
}) {
  const user = await api.post<unknown, BackendUser>('/users/', {
    username: params.username,
    password: params.password,
    display_name: params.displayName || params.username,
    email: params.email || '',
    role: params.role || 'viewer',
  })
  return { message: 'User created successfully' as string, newId: user?.id as number | undefined }
}

export async function editUser(params: {
  userId: number
  displayName?: string
  email?: string
  role?: string
  password?: string
}) {
  await api.put<unknown, BackendUser>(`/users/${params.userId}`, {
    display_name: params.displayName,
    email: params.email,
    role: params.role,
    password: params.password,
  })
  return { message: 'User edited successfully' as string }
}

export async function toggleUserEnabled(userId: number) {
  const data = await api.post<unknown, { message: string; enabled: boolean }>(`/users/${userId}/toggle-enabled`)
  return { message: data?.message || 'Status updated' as string }
}

export async function fetchSystemConfig(): Promise<SystemConfig> {
  const data = await api.get<unknown, SystemConfig | null>('/settings/system-config')
  return data ?? { project_name: '', system_version: '', login_page_title: '', default_role: 'viewer' }
}

export async function saveSystemConfig(params: SystemConfig) {
  const data = await api.put<unknown, SystemConfig>('/settings/system-config', params)
  return { message: 'System config saved' as string, config: data ?? params }
}

export async function fetchRoleMatrix(): Promise<{ matrix: RoleMatrixItem[] }> {
  const data = await api.get<unknown, BackendRoleMatrixResponse>('/roles/matrix')
  return { matrix: (data?.matrix ?? []).map(toRoleMatrixItem) }
}

export async function saveRoleMatrix(matrix: RoleMatrixItem[]) {
  const data = await api.put<unknown, BackendRoleMatrixResponse>('/roles/matrix', toRoleMatrixOutput(matrix))
  return { message: 'Role matrix saved' as string, matrix: (data?.matrix ?? []).map(toRoleMatrixItem) }
}
