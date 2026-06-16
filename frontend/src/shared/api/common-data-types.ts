export interface 文件夹条目 {
  id: number
  名称: string
  父文件夹id: number | null
}
export interface 文件解析结果 {
  [key: string]: unknown
}

export interface 公告条目 {
  id: number
  标题: string
  类型: string
  是否已读: boolean
  发布时间: string
  [key: string]: unknown
}

export interface 系统日志条目 {
  id: number
  级别: string
  分类: string
  消息: string
  创建时间: string
  [key: string]: unknown
}
export interface FileEntry {
  id: number
  文件名: string
  格式: string | null
  文件大小: number
  创建时间: string
  存储路径: string | null
  是否为文件夹?: boolean
  父文件夹id?: number | null
}

export interface 回收站条目 {
  id: number
  名称: string
  类型: '文件' | '文件夹'
  格式: string
  大小: number
  原文件夹id: number | null
  回收时间: string
}

export interface 文件详情数据 {
  id: number
  文件名: string
  格式: string
  文件大小: number
  文件夹id: number
  文件夹名称: string
  创建时间: string
  更新时间: string
  存储路径: string
  是否已回收: boolean
}

export interface 仪表盘概览数据 {
  系统版本?: string
  项目名称?: string
  用户总数?: number
  在线用户?: number
  文件总数?: number
  Agent会话数?: number
  知识库文件数?: number
}

export interface 日志条目 {
  id: number
  级别: string
  分类: string
  消息: string
  创建时间: string
}

export interface 任务条目 {
  id: number
  任务类型: string
  所属模块: string
  状态: string
  优先级: number
  参数: string | null
  结果: string | null
  错误信息: string | null
  重试次数: number
  最大重试次数: number
  创建时间: string
  开始时间: string | null
  完成时间: string | null
  创建者id: number | null
}

export interface 系统配置数据 {
  项目名称: string
  系统版本: string
  登录页标题: string
  默认角色: string
}

export interface 角色矩阵项 {
   角色: string
   名称: string
   用户管理: boolean
   系统配置: boolean
   角色矩阵: boolean
}

export interface Agent会话条目 {
  id: number
  会话标识: string
  标题: string
  消息总数: number
  创建时间: string
}
export interface 对话消息条目 {
  id: number
  类型: string
  内容: string
  思维内容?: string
  创建时间: string
}

export interface 知识条目 {
  块ID: number; 标题: string; 摘要: string; 文件ID: number
  文件名: string | null; 文档类型: string | null; 格式?: string | null; 大分类: string | null; 创建时间: string
  评分?: number; 来源类型?: string; 排序解释?: string; 页码?: number
  匹配详情?: Record<string, unknown> | null
  内容文本?: string; 页标题?: string; 页面摘要?: string
  主体JSON?: string | null; 属性JSON?: string | null; 标签JSON?: string | null
  文件夹ID?: number; 路径ID列表?: number[]; 融合ID?: number; 处理状态?: string | null
}

export interface 编目条目 {
  文件ID: number; 文件名: string | null; 格式: string | null
  大分类: string | null; 文档类型: string | null; 处理通道: string | null
  处理状态: string | null; 错误信息: string | null; 编目时间: string | null
  进度?: 知识进度
}

export interface 知识库任务条目 {
  任务ID: number; 文件ID: number; 文件名: string | null; 通道: string | null
  优先级: number; 状态: string; 入队时间: string
  开始时间: string | null; 结束时间: string | null; 错误信息: string | null
  进度?: 知识进度
}

export interface 知识进度 {
  百分比: number; 当前步骤: string; 块数: number; 候选数: number; 证据数: number
  阶段列表: Array<{ 名称: string; 状态: string }>
}
