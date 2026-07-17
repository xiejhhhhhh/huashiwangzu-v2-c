/**
 * 图标网格模型 - 纯逻辑坐标系
 *
 * 设计思路：
 * 1. 桌面是一个 M行 × N列 的逻辑网格
 * 2. 每个图标占一个格子，坐标为 (row, col)
 * 3. 拖拽释放时计算最近可用格子 → 吸附
 * 4. 渲染时 (row, col) → 像素坐标（纯算术，不查DOM）
 * 5. 持久化存 {key: {row, col}}，不存像素
 *
 * 与旧 drag-tool.ts 的区别：
 * - 旧：DOM查询 getBoundingClientRect → 像素运算 → transform偏移
 * - 新：纯数学模型 → 行列坐标 → CSS grid/绝对定位渲染
 */
import { reactive, computed } from 'vue'
import { desktopConfig, ICON_SIZE_MAP, type IconSize } from './desktop-preferences'

// ═══════════════════════════════════════════════════
// 类型
// ═══════════════════════════════════════════════════

export interface GridCell {
  row: number
  col: number
}

export interface GridMetrics {
  /** 网格起始偏移X（左侧留白） */
  originX: number
  /** 网格起始偏移Y（顶部留白） */
  originY: number
  /** 单元格宽（含间距） */
  cellWidth: number
  /** 单元格高（含间距） */
  cellHeight: number
  /** 列数 */
  cols: number
  /** 行数 */
  rows: number
  /** 图标可视宽 */
  iconWidth: number
  /** 图标可视高 */
  iconHeight: number
}

// ═══════════════════════════════════════════════════
// 图标位置注册表（纯逻辑状态）
// ═══════════════════════════════════════════════════

/** key → GridCell 映射，运行时唯一真相 */
const iconGridPositions = reactive<Record<string, GridCell>>({})

/** 已占用格子集合（用 "row:col" 字符串做快速查询） */
function occupiedSet(excludeKeys?: string[]): Set<string> {
  const excluded = new Set(excludeKeys || [])
  const set = new Set<string>()
  for (const [key, cell] of Object.entries(iconGridPositions)) {
    if (excluded.has(key)) continue
    set.add(`${cell.row}:${cell.col}`)
  }
  return set
}

// ═══════════════════════════════════════════════════
// 网格度量计算
// ═══════════════════════════════════════════════════

const GRID_PADDING_X = 18
const GRID_PADDING_Y = 14

/**
 * 根据容器尺寸和当前配置计算网格度量
 * containerWidth/containerHeight 应该是桌面可用区域（去掉任务栏）
 */
export function computeGridMetrics(containerWidth: number, containerHeight: number): GridMetrics {
  const sizeData = ICON_SIZE_MAP[desktopConfig.iconSize]
  const gap = desktopConfig.iconGridGap
  const cellWidth = sizeData.width + gap
  const cellHeight = sizeData.height + gap
  const availableWidth = containerWidth - GRID_PADDING_X * 2
  const availableHeight = containerHeight - GRID_PADDING_Y * 2
  const cols = Math.max(1, Math.floor(availableWidth / cellWidth))
  const rows = Math.max(1, Math.floor(availableHeight / cellHeight))

  return {
    originX: Math.max(GRID_PADDING_X, containerWidth - GRID_PADDING_X - ((cols - 1) * cellWidth + sizeData.width)),
    originY: GRID_PADDING_Y,
    cellWidth,
    cellHeight,
    cols,
    rows,
    iconWidth: sizeData.width,
    iconHeight: sizeData.height,
  }
}

/**
 * 像素坐标 → 最近格子
 */
export function pixelToCell(px: number, py: number, metrics: GridMetrics): GridCell {
  const col = Math.max(0, Math.min(
    Math.round((px - metrics.originX) / metrics.cellWidth),
    metrics.cols - 1
  ))
  const row = Math.max(0, Math.min(
    Math.round((py - metrics.originY) / metrics.cellHeight),
    metrics.rows - 1
  ))
  return { row, col }
}

/**
 * 格子 → 像素坐标（左上角）
 */
export function cellToPixel(cell: GridCell, metrics: GridMetrics): { x: number; y: number } {
  return {
    x: metrics.originX + cell.col * metrics.cellWidth,
    y: metrics.originY + cell.row * metrics.cellHeight,
  }
}

/**
 * 找最近的空闲格子
 * 从目标格子出发，螺旋扫描
 */
export function findNearestFreeCell(
  target: GridCell,
  metrics: GridMetrics,
  excludeKeys?: string[],
): GridCell {
  const occupied = occupiedSet(excludeKeys)
  const key = `${target.row}:${target.col}`
  if (!occupied.has(key)) return target

  // 螺旋搜索
  for (let radius = 1; radius < Math.max(metrics.rows, metrics.cols); radius++) {
    for (let dr = -radius; dr <= radius; dr++) {
      for (let dc = -radius; dc <= radius; dc++) {
        if (Math.abs(dr) !== radius && Math.abs(dc) !== radius) continue
        const r = target.row + dr
        const c = target.col + dc
        if (r < 0 || r >= metrics.rows || c < 0 || c >= metrics.cols) continue
        if (!occupied.has(`${r}:${c}`)) return { row: r, col: c }
      }
    }
  }
  return target
}

/**
 * 自动排列：从右上开始，按列从上到下，再向左换列。
 */
export function autoArrangePositions(keys: string[], metrics: GridMetrics): Record<string, GridCell> {
  const result: Record<string, GridCell> = {}
  let row = 0
  let col = metrics.cols - 1
  for (const key of keys) {
    result[key] = { row, col }
    row++
    if (row >= metrics.rows) {
      row = 0
      col--
      if (col < 0) col = 0
    }
  }
  return result
}

// ═══════════════════════════════════════════════════
// 公共接口
// ═══════════════════════════════════════════════════

export function useIconGrid() {
  return {
    /** 图标位置注册表 */
    positions: iconGridPositions,

    /** 设置单个图标位置 */
    setPosition(key: string, cell: GridCell): void {
      iconGridPositions[key] = { ...cell }
    },

    /** 批量设置 */
    setPositions(map: Record<string, GridCell>): void {
      for (const [key, cell] of Object.entries(map)) {
        iconGridPositions[key] = { ...cell }
      }
    },

    /** 移除图标（从桌面删除时） */
    removePosition(key: string): void {
      delete iconGridPositions[key]
    },

    /** 获取图标位置 */
    getPosition(key: string): GridCell | undefined {
      return iconGridPositions[key]
    },

    /** 查询格子是否被占用 */
    isCellOccupied(cell: GridCell, excludeKey?: string): boolean {
      const occupied = occupiedSet(excludeKey ? [excludeKey] : [])
      return occupied.has(`${cell.row}:${cell.col}`)
    },

    /** 从持久化数据恢复 */
    restoreFromPersisted(saved: Record<string, { row?: number; col?: number }>): void {
      for (const [key, pos] of Object.entries(saved)) {
        if (typeof pos.row === 'number' && typeof pos.col === 'number') {
          iconGridPositions[key] = { row: pos.row, col: pos.col }
        }
      }
    },

    /** 导出为可持久化格式 */
    exportPositions(): Record<string, GridCell> {
      return JSON.parse(JSON.stringify(iconGridPositions))
    },

    /** 清空所有位置 */
    clearAll(): void {
      Object.keys(iconGridPositions).forEach(k => delete iconGridPositions[k])
    },

    // 工具函数直接暴露
    computeGridMetrics,
    pixelToCell,
    cellToPixel,
    findNearestFreeCell,
    autoArrangePositions,
  }
}
