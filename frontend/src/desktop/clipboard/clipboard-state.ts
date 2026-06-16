/**
 * 剪贴板状态 — 复制/剪切/粘贴
 *
 * 使用说明：
 * - 复制/剪切时自动清空上一次剪贴板状态
 * - 剪切后图标置半透明，粘贴后恢复
 * - 再次复制/剪切自动清除上一次
 */

import { reactive, computed } from 'vue'

export interface ClipboardItem {
  id: number
  type: '文件' | '文件夹'
  名称: string
  /** 复制时的原始路径（如 /桌面/文件夹/文件.txt），用于计算粘贴后的新路径 */
  原始路径?: string
}

interface 剪贴板状态 {
  type: 'copy' | 'cut' | null
  items: ClipboardItem[]
}

const 状态 = reactive<剪贴板状态>({
  type: null,
  items: [],
})

/** 设置剪贴板内容为复制 */
export function 复制(项: ClipboardItem[]): void {
  状态.type = 'copy'
  状态.items = 项
}

/** 设置剪贴板内容为剪切 */
export function 剪切(项: ClipboardItem[]): void {
  状态.type = 'cut'
  状态.items = 项
}

/** 清空剪贴板 */
export function 清空(): void {
  状态.type = null
  状态.items = []
}

/** 剪贴板hasContent */
export const hasContent = computed(() => 状态.type !== null && 状态.items.length > 0)

/** 当前剪贴板类型 */
export const 当前类型 = computed(() => 状态.type)

/** 当前剪贴板条目 */
export const 当前条目 = computed(() => 状态.items)

/** 判断指定 id 的条目是否在剪贴板中（用于剪切半透明视觉反馈） */
export function 是否为剪切项(id: number): boolean {
  return 状态.type === 'cut' && 状态.items.some(i => i.id === id)
}

/** 获取剪贴板条目 id 列表 */
export function 获取剪贴板ID列表(): number[] {
  return 状态.items.map(i => i.id)
}
