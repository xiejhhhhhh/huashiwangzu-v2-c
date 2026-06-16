import { reactive, ref } from 'vue'
import { API_BASE_URL } from '@/shared/api'
import { 读取桌面状态请求, 保存桌面状态请求 } from '@/shared/api/desktop'
import type { DesktopWindowSnapshot } from './desktop-session-storage'

export interface DesktopPersistentState {
  版本: number
  窗口: DesktopWindowSnapshot[]
  应用状态: Record<string, Record<string, unknown>>
}

const 状态 = reactive<DesktopPersistentState>({ 版本: 1, 窗口: [], 应用状态: {} })
const 已加载 = ref(false)
let 保存定时器: ReturnType<typeof setTimeout> | null = null

export async function loadDesktopState() {
  const 响应 = await 读取桌面状态请求()
  if (响应.success && 响应.data) {
    状态.窗口 = Array.isArray(响应.data.窗口) ? 响应.data.窗口 : []
    状态.应用状态 = 响应.data.应用状态 || {}
  }
  已加载.value = true
  return 状态
}

export function updateWindowSnapshot(窗口: DesktopWindowSnapshot[]) {
  状态.窗口 = 窗口
  安排保存桌面状态()
}

export function readAppState<T>(应用标识: string, 状态名: string, 默认值: T): T {
  return (状态.应用状态[应用标识]?.[状态名] as T | undefined) ?? 默认值
}

export function 更新应用状态(应用标识: string, 状态名: string, 值: unknown) {
  if (!状态.应用状态[应用标识]) 状态.应用状态[应用标识] = {}
  状态.应用状态[应用标识][状态名] = 值
  安排保存桌面状态()
}

export function 安排保存桌面状态() {
  if (!已加载.value) return
  if (保存定时器) clearTimeout(保存定时器)
  保存定时器 = setTimeout(立即保存桌面状态, 180)
}

export function 立即保存桌面状态() {
  if (!已加载.value) return Promise.resolve()
  if (保存定时器) clearTimeout(保存定时器)
  保存定时器 = null
  return 保存桌面状态请求(JSON.parse(JSON.stringify(状态))).then(() => undefined)
}

export function 保活保存桌面状态() {
  if (!已加载.value) return
  void fetch(`${API_BASE_URL}/desktop/state`, {
    method: 'POST', credentials: 'include', keepalive: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state_json: 状态 }),
  })
}

export const 桌面状态仓库 = { 状态, 已加载 }
