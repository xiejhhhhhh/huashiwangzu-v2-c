const 后端关键词映射: [RegExp, string][] = [
  [/SQLSTATE/i, '系统内部错误'],
  [/exception/i, '系统内部错误'],
  [/syntax error/i, '系统内部错误'],
  [/Call to undefined/i, '系统内部错误'],
  [/stack trace/i, ''],
  [/#\d+\s+\/var\//i, ''],
  [/Undefined variable/i, '系统内部错误'],
  [/Division by zero/i, '系统内部错误'],
  [/Class not found/i, '系统内部错误'],
  [/RuntimeException/i, '系统内部错误'],
  [/QueryException/i, '数据查询出错'],
  [/InvalidArgumentException/i, '参数不对，请重试'],
  [/ModelNotFoundException/i, '内容不存在'],
]

const 工具友好名映射: Record<string, string> = {
  knowledge: '资料',
  knowledge_search: '资料',
  knowledge_evidence: '证据',
  dictionary: '词典',
  file: '文件',
  file_preview: '文件',
  get_weather: '天气',
  get_time: '时间',
  calculate: '计算',
}

export function 友好化错误信息(原文: string): string {
  if (!原文) return '系统开小差了，请稍后再试'
  for (const [正则, 替换] of 后端关键词映射) {
    if (正则.test(原文)) return 替换 || ''
  }
  return 原文
}

export function 工具友好名(工具名: string): string {
  return 工具友好名映射[工具名] || 工具名
}

export function 工具调用友好提示(工具名: string, 类型: string): string {
  const 名字 = 工具友好名(工具名)
  if (类型 === 'start') return `正在查${名字}...`
  if (类型 === 'success') return `已查到${名字}`
  if (类型 === 'error') return `查${名字}时出错了`
  return ''
}

export function 工具未找到来源提示(): string {
  return '未找到可用来源'
}

export function 模型不可用提示(): string {
  return 'AI 服务暂时连不上，请稍后再试，或联系管理员检查模型服务'
}
