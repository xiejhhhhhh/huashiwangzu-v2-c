/**
 * 图标网格拖拽逻辑 - 基于逻辑网格坐标
 *
 * 职责：
 * 1. 管理拖拽状态（是否拖拽中、拖拽的图标、幽灵位置、目标格子）
 * 2. 创建幽灵元素（拖拽时跟随鼠标的半透明副本）
 * 3. 计算目标格子并暴露给模板做高亮
 * 4. 释放时返回结果让父组件决定吸附或移入文件夹
 */
import { reactive, type Ref, onUnmounted } from 'vue'
import type { GridMetrics, GridCell } from '@/desktop/config/icon-grid-model'
import { pixelToCell, findNearestFreeCell } from '@/desktop/config/icon-grid-model'

// ═══════════════════════════════════════════════════
// 类型
// ═══════════════════════════════════════════════════

export interface DragResult {
  /** 被拖拽的图标键列表 */
  keys: string[]
  /** 目标格子（主图标的落点） */
  targetCell: GridCell
  /** 目标格子上是否有文件夹 */
  isDropOnFolder: boolean
  /** 文件夹图标键（如果落在文件夹上） */
  folderKey: string | null
  /** 是否落在窗口上（桌面图标拖到打开的文件夹窗口） */
  isDropOnWindow: boolean
  /** 目标窗口ID */
  targetWindowId: string | null
}

export interface IconGridDragState {
  isDragging: boolean
  draggedKeys: string[]
  ghostX: number
  ghostY: number
  targetCell: GridCell | null
  /** 高亮的文件夹键（拖到文件夹上时） */
  highlightFolderKey: string | null
  /** 当前悬停的窗口ID（拖到窗口上时） */
  hoverWindowId: string | null
}

// ═══════════════════════════════════════════════════
// 拖拽阈值
// ═══════════════════════════════════════════════════

const DRAG_THRESHOLD = 4

// ═══════════════════════════════════════════════════
// Composable
// ═══════════════════════════════════════════════════

export function useIconGridDrag(
  containerRef: Ref<HTMLElement | null>,
  metricsRef: Ref<GridMetrics | null>,
  emit: {
    onDragEnd: (result: DragResult) => void
  },
) {
  const state = reactive<IconGridDragState>({
    isDragging: false,
    draggedKeys: [],
    ghostX: 0,
    ghostY: 0,
    targetCell: null,
    highlightFolderKey: null,
    hoverWindowId: null,
  })

  // 内部追踪
  let startX = 0
  let startY = 0
  let grabOffsetX = 0
  let grabOffsetY = 0
  let ghostEl: HTMLElement | null = null
  let highlightedWindow: HTMLElement | null = null
  /** 记录哪些格子上有文件夹 */
  let folderCellMap: Map<string, string> = new Map()

  /**
   * 设置文件夹位置映射（父组件在渲染时调用）
   * key: "row:col"  value: 文件夹图标键
   */
  function setFolderCellMap(map: Map<string, string>): void {
    folderCellMap = map
  }

  /**
   * 开始追踪拖拽（mousedown时调用）
   */
  function beginTracking(keys: string[], clientX: number, clientY: number, iconEl: HTMLElement): void {
    startX = clientX
    startY = clientY
    // 计算抓取偏移（鼠标相对图标左上角）
    const rect = iconEl.getBoundingClientRect()
    grabOffsetX = clientX - rect.left
    grabOffsetY = clientY - rect.top

    const handleMove = (e: MouseEvent) => {
      const dx = e.clientX - startX
      const dy = e.clientY - startY
      if (!state.isDragging && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
        activateDrag(keys, e.clientX, e.clientY)
      }
      if (state.isDragging) {
        updateDrag(e.clientX, e.clientY)
      }
    }

    const handleUp = (e: MouseEvent) => {
      document.removeEventListener('mousemove', handleMove)
      document.removeEventListener('mouseup', handleUp)
      if (state.isDragging) {
        finishDrag(e.clientX, e.clientY)
      }
    }

    document.addEventListener('mousemove', handleMove)
    document.addEventListener('mouseup', handleUp)
  }

  /**
   * 真正进入拖拽模式
   */
  function activateDrag(keys: string[], clientX: number, clientY: number): void {
    state.isDragging = true
    state.draggedKeys = [...keys]
    state.ghostX = clientX - grabOffsetX
    state.ghostY = clientY - grabOffsetY
    document.body.classList.add('desktop-grid-dragging')
    createGhost(keys)
  }

  /**
   * 拖拽移动时更新
   */
  function updateDrag(clientX: number, clientY: number): void {
    state.ghostX = clientX - grabOffsetX
    state.ghostY = clientY - grabOffsetY
    // 更新幽灵位置
    if (ghostEl) {
      ghostEl.style.left = `${state.ghostX}px`
      ghostEl.style.top = `${state.ghostY}px`
    }

    // 先检测是否拖到了打开的窗口上（优先级高于网格格子）
    const windowEl = detectWindowAtPoint(clientX, clientY)
    if (windowEl) {
      setHighlightedWindow(windowEl)
      state.hoverWindowId = windowEl.getAttribute('data-window-id') || windowEl.closest('.desktop-window')?.getAttribute('data-window-id') || null
      state.targetCell = null
      state.highlightFolderKey = null
      return
    }
    setHighlightedWindow(null)
    state.hoverWindowId = null

    // 计算目标格子
    const container = containerRef.value
    const metrics = metricsRef.value
    if (!container || !metrics) return
    const containerRect = container.getBoundingClientRect()
    const relX = clientX - containerRect.left
    const relY = clientY - containerRect.top
    const cell = pixelToCell(relX, relY, metrics)
    state.targetCell = cell
    // 判断是否在文件夹上
    const cellKey = `${cell.row}:${cell.col}`
    const folderKey = folderCellMap.get(cellKey) || null
    // 不能拖到自己身上
    if (folderKey && state.draggedKeys.includes(folderKey)) {
      state.highlightFolderKey = null
    } else {
      state.highlightFolderKey = folderKey
    }
  }

  /**
   * 检测鼠标位置是否在某个打开的桌面窗口上
   * 只检测文件管理器类型的窗口（appKey=desktop 或有 data-accepts-drop）
   */
  function detectWindowAtPoint(clientX: number, clientY: number): HTMLElement | null {
    const windows = document.querySelectorAll('.desktop-window:not(.desktop-window-minimized)')
    // 按 z-index 从高到低排序检测
    const sorted = Array.from(windows).sort((a, b) => {
      const za = parseInt((a as HTMLElement).style.zIndex || '0')
      const zb = parseInt((b as HTMLElement).style.zIndex || '0')
      return zb - za
    })
    for (const win of sorted) {
      const rect = win.getBoundingClientRect()
      if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
        // 只接受有 data-accepts-drop 属性或 appKey 为 desktop 的窗口
        const el = win as HTMLElement
        if (el.getAttribute('data-accepts-drop') === 'true' || el.querySelector('.file-list-area')) {
          return el
        }
      }
    }
    return null
  }

  /**
   * 释放拖拽
   */
  function finishDrag(clientX: number, clientY: number): void {
    const container = containerRef.value
    const metrics = metricsRef.value
    removeGhost()
    document.body.classList.remove('desktop-grid-dragging')

    let targetCell: GridCell = { row: 0, col: 0 }
    let isDropOnFolder = false
    let folderKey: string | null = null
    let isDropOnWindow = false
    let targetWindowId: string | null = null

    // 先检查是否落在窗口上
    const windowEl = detectWindowAtPoint(clientX, clientY)
    if (windowEl) {
      isDropOnWindow = true
      targetWindowId = windowEl.getAttribute('data-window-id') || windowEl.closest('.desktop-window')?.getAttribute('data-window-id') || null
    } else if (container && metrics) {
      const containerRect = container.getBoundingClientRect()
      const relX = clientX - containerRect.left
      const relY = clientY - containerRect.top
      const cell = pixelToCell(relX, relY, metrics)
      // 检查是否落在文件夹上
      const cellStr = `${cell.row}:${cell.col}`
      const fKey = folderCellMap.get(cellStr) || null
      if (fKey && !state.draggedKeys.includes(fKey)) {
        isDropOnFolder = true
        folderKey = fKey
        targetCell = cell
      } else {
        // 找最近空格子吸附
        targetCell = findNearestFreeCell(cell, metrics, state.draggedKeys)
      }
    }

    const result: DragResult = {
      keys: [...state.draggedKeys],
      targetCell,
      isDropOnFolder,
      folderKey,
      isDropOnWindow,
      targetWindowId,
    }

    // 重置状态
    state.isDragging = false
    state.draggedKeys = []
    state.targetCell = null
    state.highlightFolderKey = null
    state.hoverWindowId = null
    setHighlightedWindow(null)

    emit.onDragEnd(result)
  }

  /**
   * 创建幽灵元素（半透明图标副本跟随鼠标）
   */
  function createGhost(keys: string[]): void {
    removeGhost()
    const el = document.createElement('div')
    el.className = 'desktop-icon-drag-ghost'
    el.style.position = 'fixed'
    el.style.left = `${state.ghostX}px`
    el.style.top = `${state.ghostY}px`
    el.style.zIndex = '99999'
    el.style.pointerEvents = 'none'
    el.style.opacity = '0.7'
    el.style.transition = 'none'
    // 克隆第一个拖拽图标的内容作为幽灵显示
    const primaryEl = document.querySelector(`[data-grid-key="${keys[0]}"]`) as HTMLElement | null
    if (primaryEl) {
      const clone = primaryEl.cloneNode(true) as HTMLElement
      clone.style.position = 'static'
      clone.style.transform = 'none'
      clone.style.opacity = '1'
      el.appendChild(clone)
      // 多个图标时显示计数徽章
      if (keys.length > 1) {
        const badge = document.createElement('span')
        badge.className = 'desktop-icon-drag-badge'
        badge.textContent = String(keys.length)
        el.appendChild(badge)
      }
    }
    document.body.appendChild(el)
    ghostEl = el
  }

  /**
   * 移除幽灵元素
   */
  function removeGhost(): void {
    if (ghostEl) {
      ghostEl.remove()
      ghostEl = null
    }
  }

  function setHighlightedWindow(windowEl: HTMLElement | null): void {
    if (highlightedWindow === windowEl) return
    highlightedWindow?.classList.remove('desktop-window-drop-target')
    highlightedWindow = windowEl
    highlightedWindow?.classList.add('desktop-window-drop-target')
  }

  // 组件卸载时清理
  onUnmounted(() => {
    removeGhost()
    setHighlightedWindow(null)
    document.body.classList.remove('desktop-grid-dragging')
  })

  return {
    state,
    beginTracking,
    setFolderCellMap,
  }
}
