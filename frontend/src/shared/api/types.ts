export interface 统一响应<T = unknown> {
  success: boolean
  data?: T | null
  error?: string | null
  errors?: any[] | null
}

export type 接口响应<T = unknown> = 统一响应<T>

export interface 登录参数 {
  username: string
  password: string
}

export interface 用户信息 {
  userId?: number
  username?: string
  displayName?: string
  email?: string
  role?: string
}

export interface 菜单项数据 {
  name: string
  path: string
  icon: string
}

export interface 分页结果<T> {
  current_page: number
  data: T[]
  last_page: number
  per_page: number
  total: number
}

export interface 系统状态条目 {
  status: boolean
  message: string
}

export interface 系统状态数据 {
  backend: 系统状态条目
  database: 系统状态条目
  worker: 系统状态条目
  modelService: 系统状态条目
  productionEntry: 系统状态条目
}

export type {
  文件夹条目, FileEntry, 回收站条目, 文件详情数据,
  仪表盘概览数据, 日志条目, 任务条目,
  系统配置数据, 角色矩阵项,
  Agent会话条目, 对话消息条目,
  知识条目, 编目条目, 知识库任务条目, 知识进度, 文件解析结果,
  公告条目, 系统日志条目,
} from './common-data-types'

export interface 薄弱类型项 {
  类型: string
  题数: number
  平均召回: number
}

export interface 评估记录 {
  记录ID: number
  总题数: number
  有答案题数: number
  无答案题数: number
  召回率: number
  MRR: number
  NDCG: number
  证据命中率: number
  拒答正确率: number
  薄弱类型: 薄弱类型项[]
  逐题详情?: any[]
  耗时ms: number
  创建时间: string
}

export type 评估记录缩略 = Omit<评估记录, '逐题详情'>
