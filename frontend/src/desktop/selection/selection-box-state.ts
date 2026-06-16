/**
 * 框选状态 — 矩形选区起点/终点/是否激活
 */
import { reactive, computed } from 'vue'

interface 框选状态 {
  active: boolean
  startX: number
  startY: number
  currentX: number
  currentY: number
}

const 状态 = reactive<框选状态>({
  active: false,
  startX: 0, startY: 0,
  currentX: 0, currentY: 0,
})

export function 开始框选(x: number, y: number): void {
  状态.active = true
  状态.startX = x
  状态.startY = y
  状态.currentX = x
  状态.currentY = y
}

export function 更新框选(x: number, y: number): void {
  if (!状态.active) return
  状态.currentX = x
  状态.currentY = y
}

export function 结束框选(): void {
  状态.active = false
}

export const 框选矩形 = computed(() => {
  const x = Math.min(状态.startX, 状态.currentX)
  const y = Math.min(状态.startY, 状态.currentY)
  const w = Math.abs(状态.currentX - 状态.startX)
  const h = Math.abs(状态.currentY - 状态.startY)
  return { x, y, w, h }
})

export const 框选是否激活 = computed(() => 状态.active)

/** 最小拖动阈值 4px，过滤单击抖动 */
export const 框选有效 = computed(() =>
  状态.active && (框选矩形.value.w > 4 || 框选矩形.value.h > 4)
)
