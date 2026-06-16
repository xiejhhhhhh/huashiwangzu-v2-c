/**
 * 拖拽工具函数 — 网格吸附 + 边界检测
 *
 * 图标是 flex 布局，不设绝对坐标。
 * 拖拽结束后通过 transform 偏移实现视觉落点，
 * 落点坐标存储用于后续持久化。
 */
import { reactive } from 'vue'

const GRID = 48
const ICON_W = 88
const ICON_H = 88
const TASKBAR_H = 48

/** 网格吸附 */
export function snapToGrid(val: number): number {
  return Math.round(val / GRID) * GRID
}

/** 边界钳制 + 网格吸附 */
export function clampIconPosition(x: number, y: number): { x: number; y: number } {
  return {
    x: snapToGrid(Math.max(0, Math.min(x, window.innerWidth - ICON_W))),
    y: snapToGrid(Math.max(0, Math.min(y, window.innerHeight - TASKBAR_H - ICON_H))),
  }
}

/**
 * 拖拽落点坐标覆盖表
 * key: data-选中标记的值（如 "file:123"）
 * value: 落点 transform 偏移 { x, y }
 *
 * 图标渲染时读取此表，有覆盖则用 transform 偏移，
 * 无覆盖则回到 flex 默认位置。
 */
export const 落点覆盖 = reactive<Record<string, { x: number; y: number }>>({})

/** 记录落点 */
export function 设置落点(标记: string, x: number, y: number): void {
  落点覆盖[标记] = { x, y }
}

/** 批量记录落点（主图标基准 + 跟随图标偏移） */
export function 批量设置落点(
  主标记: string, 主x: number, 主y: number,
  全部标记: string[], 偏移列表: { id: string; dx: number; dy: number }[]
): void {
  全部标记.forEach(标记 => {
    const 偏移 = 偏移列表.find(o => o.id === 标记)
    const { x, y } = clampIconPosition(
      标记 === 主标记 ? 主x : 主x + (偏移?.dx ?? 0),
      标记 === 主标记 ? 主y : 主y + (偏移?.dy ?? 0)
    )
    落点覆盖[标记] = { x, y }
  })
}

/** 清除落点 */
export function 清除落点(标记: string): void {
  delete 落点覆盖[标记]
}

/** 读取落点 transform 样式 */
export function 取落点样式(标记: string): string {
  const p = 落点覆盖[标记]
  return p ? `translate(${p.x}px, ${p.y}px)` : ''
}
