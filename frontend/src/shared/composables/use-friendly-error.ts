const backendKeywordMap: [RegExp, string][] = [
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

const toolFriendlyNameMap: Record<string, string> = {
  file: '文件',
  file_preview: '文件',
  get_weather: '天气',
  get_time: '时间',
  calculate: '计算',
}

export function friendlyErrorMessage(text: string): string {
  if (!text) return '系统开小差了，请稍后再试'
  for (const [regex, replacement] of backendKeywordMap) {
    if (regex.test(text)) return replacement || ''
  }
  return text
}

export function friendlyToolName(toolName: string): string {
  return toolFriendlyNameMap[toolName] || toolName
}

export function friendlyToolCallHint(toolName: string, type: string): string {
  const name = friendlyToolName(toolName)
  if (type === 'start') return `正在查${name}...`
  if (type === 'success') return `已查到${name}`
  if (type === 'error') return `查${name}时出错了`
  return ''
}

export function noSourceFoundHint(): string {
  return '未找到可用来源'
}

export function modelUnavailableHint(): string {
  return 'AI 服务暂时连不上，请稍后再试，或联系管理员检查模型服务'
}
