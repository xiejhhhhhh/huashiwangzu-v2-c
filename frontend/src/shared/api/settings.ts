import api from './index'
import type { 统一响应, 系统配置数据, 角色矩阵项 } from './types'

export interface UserEntry {
  id: number
  用户名: string
  displayName: string
  email: string
  角色: string
  状态: number
  创建时间: string
  最后登录: string
}

export interface 用户列表返回 {
  用户列表: UserEntry[]
  总数: number
}

function 转UserEntry(用户: any): UserEntry {
  return {
    id: 用户.id,
    用户名: 用户.username ?? 用户.username,
    displayName: 用户.displayName ?? 用户.display_name,
    email: 用户.email ?? 用户.email ?? '',
    角色: 用户.role ?? 用户.role,
    状态: 用户.状态 ?? (用户.enabled === false ? 0 : 1),
    创建时间: 用户.创建时间 ?? 用户.created_at ?? '',
    最后登录: 用户.最后登录 ?? 用户.last_login ?? '',
  }
}

function 转用户列表响应(响应: any): any {
  const 数据 = 响应.data ?? 响应.data ?? 响应
  const 列表 = Array.isArray(数据) ? 数据 : (数据.users ?? 数据.用户列表 ?? [])
  return { success: true, 数据: { 用户列表: 列表.map(转UserEntry), 总数: 数据.total ?? 列表.length }, error: '' }
}

function 转系统配置输入(配置: any): 系统配置数据 {
  return {
    项目名称: 配置.项目名称 ?? 配置.project_name ?? '',
    系统版本: 配置.系统版本 ?? 配置.system_version ?? '',
    登录页标题: 配置.登录页标题 ?? 配置.login_page_title ?? '',
    默认角色: 配置.默认角色 ?? 配置.default_role ?? 'viewer',
  }
}

function 转系统配置输出(配置: 系统配置数据): Record<string, string> {
  return {
    project_name: 配置.项目名称,
    system_version: 配置.系统版本,
    login_page_title: 配置.登录页标题,
    default_role: 配置.默认角色,
  }
}

function 转角色矩阵项(项: any): 角色矩阵项 {
  const 权限 = 项.权限 ?? 项.permissions ?? {}
  return {
    角色: 项.role ?? 项.role_key,
    名称: 项.名称 ?? 项.display_name,
    用户管理: !!权限.user_management,
    系统配置: !!权限.system_config,
    角色矩阵: !!权限.role_matrix,
  }
}

function 转角色矩阵输出(矩阵: 角色矩阵项[]) {
  return {
    matrix: 矩阵.map(项 => ({
      role_key: 项.角色,
      display_name: 项.名称,
      permissions: {
        user_management: 项.用户管理,
        system_config: 项.系统配置,
        role_matrix: 项.角色矩阵,
      },
    })),
  }
}

export function 获取用户列表() {
  return api.get('/users/').then(转用户列表响应)
}

export function 搜索用户(关键字: string) {
  return api.get('/users/search', { params: { keyword: 关键字 } }).then(转用户列表响应)
}

export function 创建用户(参数: {
  用户名: string
  密码: string
  displayName?: string
  email?: string
  角色?: string
}) {
  return api.post('/users/', {
    username: 参数.用户名,
    password: 参数.密码,
    display_name: 参数.displayName || 参数.用户名,
    email: 参数.email || '',
    role: 参数.角色 || 'viewer',
  }).then((res: any) => ({ success: true, 数据: { 消息: '用户创建成功', 新id: res.data?.id }, error: '' }))
}

export function 编辑用户(参数: {
  用户id: number
  displayName?: string
  email?: string
  角色?: string
  密码?: string
}) {
  return api.put(`/users/${参数.用户id}`, {
    display_name: 参数.displayName,
    email: 参数.email,
    role: 参数.角色,
    password: 参数.密码,
  }).then(() => ({ success: true, 数据: { 消息: '用户编辑成功' }, error: '' }))
}

export function 禁用用户(用户id: number) {
  return api.post(`/users/${用户id}/toggle-enabled`).then(() => ({ success: true, 数据: { 消息: '状态已更新' }, error: '' }))
}

export function 获取系统配置() {
  return api.get('/settings/system-config').then((res: any) => ({
    success: true, 数据: 转系统配置输入(res.data ?? {}), error: '',
  }))
}

export function 保存系统配置(参数: 系统配置数据) {
  return api.put('/settings/system-config', 转系统配置输出(参数)).then((res: any) => ({
    success: true, 数据: { 消息: '系统配置已保存', 配置: 转系统配置输入(res.data ?? {}) }, error: '',
  }))
}

export function 获取角色矩阵() {
  return api.get('/roles/matrix').then((res: any) => ({
    success: true, 数据: { 矩阵: (res.data?.matrix ?? []).map(转角色矩阵项) }, error: '',
  }))
}

export function 保存角色矩阵(矩阵: 角色矩阵项[]) {
  return api.put('/roles/matrix', 转角色矩阵输出(矩阵)).then((res: any) => ({
    success: true, 数据: { 消息: '角色矩阵已保存', 矩阵: (res.data?.matrix ?? []).map(转角色矩阵项) }, error: '',
  }))
}
