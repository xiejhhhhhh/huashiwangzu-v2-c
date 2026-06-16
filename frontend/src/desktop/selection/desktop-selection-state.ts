/**
 * 桌面图标选中状态 — 共享给桌面壳和图标网格
 */
import { reactive, computed } from 'vue'

interface 桌面选中状态 {
  ids: string[]  // 格式: "app:应用标识" | "file:文件id"
}

const 状态 = reactive<桌面选中状态>({ ids: [] })

export function 选中(id: string): void { 状态.ids = [id] }

export function 追加选中(id: string): void {
  if (!状态.ids.includes(id)) 状态.ids.push(id)
}

export function 批量选中(ids: string[], append = false): void {
  状态.ids = append ? [...new Set([...状态.ids, ...ids])] : ids
}

export function 取消选中(): void { 状态.ids = [] }

export function 切换选中(id: string): void {
  const idx = 状态.ids.indexOf(id)
  idx >= 0 ? 状态.ids.splice(idx, 1) : 状态.ids.push(id)
}

export function 是否选中(id: string): boolean {
  return 状态.ids.includes(id)
}

export const 选中数量 = computed(() => 状态.ids.length)
export const 选中列表 = computed(() => [...状态.ids])
export const 是否多选 = computed(() => 状态.ids.length > 1)
