export type DesktopEventTypes = {
  'file:uploaded': { 文件夹id?: number; 文件名: string }
  'file:deleted': { 类型: '文件' | '文件夹'; id: number }
  'file:restored': { 类型: '文件' | '文件夹'; id: number }
  'file:renamed': { 类型: '文件' | '文件夹'; id: number; 新名称: string }
  'file:created': { 文件夹id: number; 名称: string }
  'desktop:create-folder': { 文件夹id?: number | null }
  'desktop:upload-file': { 文件夹id?: number | null }
  'desktop:move-to-folder': { ids: string[]; 目标文件夹id: string }
  'task:completed': { 任务id: number | string; 任务类型: string }
  'notification:created': { id: number; 标题: string }
  'refresh:file-list': { 文件夹id?: number }
  'refresh:recycle-bin': void
  'app:open': { 目标应用标识: string; 参数?: Record<string, unknown> }
  'app:close': { 目标应用标识: string }
  'app:activate': { 目标应用标识: string }
  'app:event': { 目标应用标识: string; 事件名: string; 载荷?: unknown }
  'app:action': { 目标应用标识: string; 动作名: string; 参数?: Record<string, unknown> }
  'app:request': { 目标appId: string; 动作: string; 参数: Record<string, unknown>; 请求ID: string }
  'app:response': { success: boolean; 数据?: unknown; 错误?: { 码: string; 消息: string }; 请求ID?: string }
  'app:notification': { 标题: string; 内容: string; 类型?: string; 目标应用?: string }
}
