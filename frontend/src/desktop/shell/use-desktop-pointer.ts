import { onMounted, onUnmounted } from 'vue'
import { use桌面事件总线 } from '@/desktop/events/use-desktop-event-bus'
import { 开始框选, 更新框选, 结束框选, 框选矩形 } from '@/desktop/selection/selection-box-state'
import { 取消选中, 批量选中 } from '@/desktop/selection/desktop-selection-state'
import { 开始拖拽, 更新拖拽偏移, 进入文件夹, 离开文件夹, 结束拖拽, 拖拽状态 } from '@/desktop/drag-drop/drag-state'
import { clampIconPosition, 批量设置落点 } from '@/desktop/drag-drop/drag-tool'

function 框选命中(sel: { x: number; y: number; w: number; h: number }, e: MouseEvent) {
  const ids: string[] = []
  document.querySelectorAll('.桌面图标项').forEach(el => {
    const r = el.getBoundingClientRect()
    const 重叠 = !(r.right < sel.x || r.left > sel.x + sel.w || r.bottom < sel.y || r.top > sel.y + sel.h)
    const 标记 = 重叠 ? el.getAttribute('data-选中标记') : null
    if (标记) ids.push(标记)
  })
  批量选中(ids, e.ctrlKey)
}

function 检测悬停文件夹(e: MouseEvent) {
  const el = document.elementFromPoint(e.clientX, e.clientY)
  const 文件夹 = el?.closest?.('[data-是文件夹]') as HTMLElement | null
  if (!文件夹) { 离开文件夹(); return }
  const id = 文件夹.getAttribute('data-选中标记')?.replace('file:', '') || ''
  if (id && !拖拽状态.draggedIds.includes(`file:${id}`)) 进入文件夹(id)
  else 离开文件夹()
}

function 吸附拖拽图标(e: MouseEvent) {
  const 主标记 = 拖拽状态.draggedIds[0]
  if (!主标记) return
  const 主体 = document.querySelector(`[data-选中标记="${主标记}"]`)
  const 原始矩形 = 主体?.getBoundingClientRect()
  if (!原始矩形) return
  const 落点x = 原始矩形.left + e.clientX - 拖拽状态.originX
  const 落点y = 原始矩形.top + e.clientY - 拖拽状态.originY
  const { x, y } = clampIconPosition(落点x, 落点y)
  批量设置落点(主标记, x, y, 拖拽状态.draggedIds, 拖拽状态.偏移列表)
  拖拽状态.偏移列表.forEach(({ id, dx, dy }) => {
    const el = document.querySelector(`[data-选中标记="${id}"]`) as HTMLElement | null
    if (el) el.style.transform = `translate(${x + dx - 原始矩形.left}px, ${y + dy - 原始矩形.top}px)`
  })
}

export function useDesktopPointer() {
  const { emit } = use桌面事件总线()

  function 桌面鼠标按下(e: MouseEvent) {
    if (e.target !== e.currentTarget) return
    if (!e.ctrlKey) 取消选中()
    开始框选(e.clientX, e.clientY)
  }

  function 桌面鼠标移动(e: MouseEvent) {
    if (拖拽状态.isDragging) {
      更新拖拽偏移(e.clientX - 拖拽状态.originX, e.clientY - 拖拽状态.originY)
      检测悬停文件夹(e)
      return
    }
    if (!框选矩形.value.w && !框选矩形.value.h) return
    更新框选(e.clientX, e.clientY)
    const sel = 框选矩形.value
    if (sel.w >= 4 || sel.h >= 4) 框选命中(sel, e)
  }

  function 桌面鼠标放开(e: MouseEvent) {
    if (拖拽状态.isDragging) {
      const 目标文件夹 = 拖拽状态.dragOverId
      if (目标文件夹) emit('desktop:move-to-folder', { ids: 拖拽状态.draggedIds, 目标文件夹id: 目标文件夹 })
      else 吸附拖拽图标(e)
      结束拖拽()
      return
    }
    结束框选()
  }

  onMounted(() => {
    window.addEventListener('mousemove', 桌面鼠标移动)
    window.addEventListener('mouseup', 桌面鼠标放开)
  })
  onUnmounted(() => {
    window.removeEventListener('mousemove', 桌面鼠标移动)
    window.removeEventListener('mouseup', 桌面鼠标放开)
  })
  return { 桌面鼠标按下 }
}
