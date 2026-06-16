/**
 * 拖拽状态 — 桌面图标拖拽移入文件夹
 *
 * - 拖拽时记录被拖图标列表（支持框选后批量拖）
 * - 悬停文件夹 150ms 延迟触发高亮（防路过误触）
 * - 拖拽过程中禁用其他图标的 hover 样式
 */
import { reactive } from 'vue'

interface 拖拽状态 {
  isDragging: boolean
  draggedIds: string[]
  dragOverId: string | null    // 当前悬停的文件夹 id
  originX: number
  originY: number
  偏移列表: { id: string; dx: number; dy: number }[]
}

const 状态 = reactive<拖拽状态>({
  isDragging: false,
  draggedIds: [],
  dragOverId: null,
  originX: 0, originY: 0,
  偏移列表: [],
})

let _hoverTimer: ReturnType<typeof setTimeout> | null = null

export function 开始拖拽(ids: string[], x: number, y: number): void {
  状态.isDragging = true
  状态.draggedIds = ids
  状态.originX = x
  状态.originY = y
  // 记录每个图标相对起始位置的偏移
  const 主体元素 = document.querySelector(`[data-选中标记="${ids[0]}"]`)
  const 主体矩形 = 主体元素?.getBoundingClientRect()
  if (!主体矩形) { 结束拖拽(); return }
  状态.偏移列表 = ids.map(id => {
    const el = document.querySelector(`[data-选中标记="${id}"]`)
    const r = el?.getBoundingClientRect()
    return { id, dx: (r?.left ?? 0) - 主体矩形.left, dy: (r?.top ?? 0) - 主体矩形.top }
  })
  document.body.classList.add('桌面-拖拽中')
}

export function 更新拖拽偏移(dx: number, dy: number): void {
  if (!状态.isDragging) return
  状态.偏移列表.forEach(item => {
    const el = document.querySelector(`[data-选中标记="${item.id}"]`) as HTMLElement | null
    if (!el) return
    // 拖拽期间设为 fixed 跟随鼠标
    el.style.position = 'fixed'
    el.style.left = (状态.originX + item.dx + dx) + 'px'
    el.style.top = (状态.originY + item.dy + dy) + 'px'
    el.style.zIndex = '999'
    el.style.pointerEvents = 'none'
  })
}

export function 进入文件夹(id: string): void {
  if (_hoverTimer) clearTimeout(_hoverTimer)
  _hoverTimer = setTimeout(() => { 状态.dragOverId = id }, 150)
}

export function 离开文件夹(): void {
  if (_hoverTimer) clearTimeout(_hoverTimer)
  状态.dragOverId = null
}

export function 结束拖拽(): void {
  状态.isDragging = false
  状态.draggedIds = []
  状态.dragOverId = null
  状态.偏移列表 = []
  if (_hoverTimer) clearTimeout(_hoverTimer)
  document.body.classList.remove('桌面-拖拽中')
  // 恢复所有图标定位
  document.querySelectorAll('[data-选中标记]').forEach(el => {
    (el as HTMLElement).style.position = ''
    ;(el as HTMLElement).style.left = ''
    ;(el as HTMLElement).style.top = ''
    ;(el as HTMLElement).style.zIndex = ''
    ;(el as HTMLElement).style.pointerEvents = ''
  })
}

export const 拖拽状态 = 状态
