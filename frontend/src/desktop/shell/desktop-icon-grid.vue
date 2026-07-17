<template>
  <div ref="containerRef" class="desktop-icon-grid">
    <!-- 拖拽目标格子高亮 -->
    <div
      v-if="dragState.isDragging && dragState.targetCell && !dragState.highlightFolderKey"
      class="desktop-icon-grid-target-highlight"
      :style="targetHighlightStyle"
    />

    <!-- 应用图标 -->
    <div
      v-for="app in appList"
      :key="app.appKey"
      class="desktop-icon-item desktop-app-icon-item"
      :class="iconItemClasses(`app:${app.appKey}`)"
      :data-grid-key="`app:${app.appKey}`"
      :data-selection-key="`app:${app.appKey}`"
      :style="getIconPositionStyle(`app:${app.appKey}`)"
      @mousedown.stop="handleIconMouseDown(`app:${app.appKey}`, $event)"
      @click="handleAppClick(app.appKey, $event)"
      @dblclick.stop="handleAppDoubleClick(app.appKey)"
      tabindex="0"
      role="button"
      @keydown.enter.prevent="$emit('openApp', app.appKey)"
      @contextmenu.prevent.stop="handleAppContextMenu(app.appKey, $event)"
    >
      <div class="desktop-icon-image" :style="iconImageStyle">
        <AppIcon :icon="app.icon" :app-key="app.appKey" :size="currentIconImageSize" />
      </div>
      <span v-if="desktopConfig.showIconLabels" class="desktop-icon-label" :style="labelStyle">
        {{ app.appName }}
      </span>
    </div>

    <!-- 文件图标 -->
    <div
      v-for="file in fileList"
      :key="`file-${file.id}`"
      class="desktop-icon-item desktop-file-icon-item"
      :class="iconItemClasses(`file:${file.id}`, file.is_folder)"
      :data-grid-key="`file:${file.id}`"
      :data-selection-key="`file:${file.id}`"
      :data-folder="file.is_folder ? String(file.id) : undefined"
      :style="getIconPositionStyle(`file:${file.id}`)"
      @mousedown.stop="handleIconMouseDown(`file:${file.id}`, $event)"
      @click="handleFileClick(file, $event)"
      @dblclick.stop="handleFileDoubleClick(file)"
      tabindex="0"
      role="button"
      @keydown.enter.prevent="$emit('openFile', file)"
      @contextmenu.prevent.stop="handleFileContextMenu(file, $event)"
    >
      <div class="desktop-icon-image" :style="iconImageStyle">
        <FileVisualIcon
          :kind="file.is_folder || !file.format ? 'folder' : 'file'"
          :extension="file.format || ''"
          :size="currentIconImageSize"
        />
      </div>
      <span v-if="desktopConfig.showIconLabels" class="desktop-icon-label" :style="labelStyle">
        {{ getFileName(file) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import type { FileEntry } from '@/shared/api/types'
import type { GridMetrics, GridCell } from '@/desktop/config/icon-grid-model'
import AppIcon from '@/desktop/components/app-icon.vue'
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import { isSelected, select, toggleSelection, selectedIds } from '@/desktop/selection/desktop-selection-state'
import { formatFileDisplayName } from '@/shared/files/display-name'
import { desktopConfig, ICON_SIZE_MAP } from '@/desktop/config/desktop-preferences'
import {
  useIconGrid,
  computeGridMetrics,
  cellToPixel,
  autoArrangePositions,
  findNearestFreeCell,
} from '@/desktop/config/icon-grid-model'
import { useIconGridDrag, type DragResult } from './use-icon-grid-drag'
import { animateBounce, animateFlash } from '@/desktop/feedback/desktop-feedback'
import './desktop-icon-grid.css'

// ═══════════════════════════════════════════════════
// Props / Emits
// ═══════════════════════════════════════════════════

const props = defineProps<{
  appList: AppRegistryEntry[]
  fileList?: FileEntry[]
}>()

const emit = defineEmits<{
  (e: 'openApp', appKey: string): void
  (e: 'openFile', file: FileEntry): void
  (e: 'app-context-menu', appKey: string, event: MouseEvent): void
  (e: 'file-context-menu', file: FileEntry, event: MouseEvent): void
  (e: 'move-to-folder', keys: string[], folderKey: string): void
  (e: 'drop-on-window', keys: string[], windowId: string): void
}>()

// ═══════════════════════════════════════════════════
// 网格系统
// ═══════════════════════════════════════════════════

const containerRef = ref<HTMLElement | null>(null)
const metrics = ref<GridMetrics | null>(null)
const { positions, setPosition, setPositions, getPosition } = useIconGrid()

// 当前图标尺寸相关计算
const currentSizeData = computed(() => ICON_SIZE_MAP[desktopConfig.iconSize])
const currentIconImageSize = computed(() => currentSizeData.value.imageSize)
const iconImageStyle = computed(() => ({
  width: `${currentSizeData.value.imageSize}px`,
  height: `${currentSizeData.value.imageSize}px`,
}))
const labelStyle = computed(() => ({
  fontSize: `${currentSizeData.value.fontSize}px`,
  maxWidth: `${currentSizeData.value.width - 8}px`,
}))

// ═══════════════════════════════════════════════════
// 容器尺寸监听
// ═══════════════════════════════════════════════════

let resizeObserver: ResizeObserver | null = null

function updateMetrics(): void {
  const el = containerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (rect.width > 0 && rect.height > 0) {
    metrics.value = computeGridMetrics(rect.width, rect.height)
  }
}

onMounted(() => {
  updateMetrics()
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      updateMetrics()
      // 尺寸变化后重新排列未注册的图标
      nextTick(() => ensureAllPositioned())
    })
    resizeObserver.observe(containerRef.value)
  }
  // 初始分配位置
  nextTick(() => ensureAllPositioned())
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

// ═══════════════════════════════════════════════════
// 图标位置管理
// ═══════════════════════════════════════════════════

/** 所有图标的键列表 */
const allIconKeys = computed(() => {
  const keys: string[] = []
  for (const app of props.appList) keys.push(`app:${app.appKey}`)
  if (props.fileList) {
    for (const file of props.fileList) keys.push(`file:${file.id}`)
  }
  return keys
})

/** 确保所有图标都有位置 */
function ensureAllPositioned(): void {
  const m = metrics.value
  if (!m) return
  if (desktopConfig.iconLayout === 'auto-arrange') {
    setPositions(autoArrangePositions(allIconKeys.value, m))
    return
  }
  const unpositioned: string[] = []
  for (const key of allIconKeys.value) {
    if (!getPosition(key)) unpositioned.push(key)
  }
  if (unpositioned.length > 0) {
    for (const key of unpositioned) {
      const cell = findNearestFreeCell({ row: 0, col: m.cols - 1 }, m, [key])
      setPosition(key, cell)
    }
  }
}

// 监听列表变化
watch(allIconKeys, () => {
  nextTick(() => ensureAllPositioned())
})

// 监听图标尺寸变化：重算网格度量，重排位置
watch(() => desktopConfig.iconSize, () => {
  updateMetrics()
  nextTick(() => {
    if (desktopConfig.iconLayout === 'auto-arrange' && metrics.value) {
      const arranged = autoArrangePositions(allIconKeys.value, metrics.value)
      setPositions(arranged)
    }
  })
})

// ═══════════════════════════════════════════════════
// 位置样式计算
// ═══════════════════════════════════════════════════

function getIconPositionStyle(key: string): Record<string, string> {
  const cell = getPosition(key)
  const m = metrics.value
  if (!cell || !m) return { left: '0px', top: '0px', width: `${currentSizeData.value.width}px` }
  const { x, y } = cellToPixel(cell, m)
  return {
    left: `${x}px`,
    top: `${y}px`,
    width: `${currentSizeData.value.width}px`,
  }
}

// 目标格子高亮样式
const targetHighlightStyle = computed(() => {
  const cell = dragState.targetCell
  const m = metrics.value
  if (!cell || !m) return { display: 'none' }
  const { x, y } = cellToPixel(cell, m)
  return {
    left: `${x}px`,
    top: `${y}px`,
    width: `${m.iconWidth}px`,
    height: `${m.iconHeight}px`,
  }
})

// ═══════════════════════════════════════════════════
// 拖拽
// ═══════════════════════════════════════════════════

const { state: dragState, beginTracking, setFolderCellMap } = useIconGridDrag(
  containerRef,
  metrics,
  { onDragEnd: handleDragEnd },
)

/** 更新文件夹格子映射（让拖拽模块知道哪些格子有文件夹） */
function updateFolderMap(): void {
  const map = new Map<string, string>()
  if (props.fileList) {
    for (const file of props.fileList) {
      if (!file.is_folder) continue
      const key = `file:${file.id}`
      const cell = getPosition(key)
      if (cell) map.set(`${cell.row}:${cell.col}`, key)
    }
  }
  setFolderCellMap(map)
}

// 监听文件列表和位置变化以更新文件夹映射
watch([() => props.fileList, positions], () => {
  nextTick(() => updateFolderMap())
}, { deep: true, immediate: true })

function handleDragEnd(result: DragResult): void {
  if (result.isDropOnWindow && result.targetWindowId) {
    // 拖到打开的文件夹窗口
    emit('drop-on-window', result.keys, result.targetWindowId)
  } else if (result.isDropOnFolder && result.folderKey) {
    // 移入文件夹
    emit('move-to-folder', result.keys, result.folderKey)
    // 文件夹闪烁反馈
    const folderEl = containerRef.value?.querySelector(
      `[data-grid-key="${result.folderKey}"]`
    ) as HTMLElement | null
    animateFlash(folderEl)
  } else {
    // 吸附到格子
    const m = metrics.value
    if (!m) return
    // 主图标设定到目标格子
    const primaryKey = result.keys[0]
    setPosition(primaryKey, result.targetCell)
    // 多选时其余图标找邻近空格
    for (let i = 1; i < result.keys.length; i++) {
      const nearby = findNearestFreeCell(result.targetCell, m, result.keys.slice(0, i + 1))
      setPosition(result.keys[i], nearby)
    }
    // 吸附弹跳反馈
    nextTick(() => {
      for (const key of result.keys) {
        const el = containerRef.value?.querySelector(`[data-grid-key="${key}"]`) as HTMLElement | null
        animateBounce(el, 0.95)
      }
    })
  }
}

// ═══════════════════════════════════════════════════
// 交互
// ═══════════════════════════════════════════════════

let suppressNextClick = false

function handleIconMouseDown(key: string, e: MouseEvent): void {
  if (e.button !== 0) return
  const iconEl = (e.currentTarget as HTMLElement)
  const isToggleGesture = e.ctrlKey || e.metaKey
  // 判断是否需要拖拽多个
  const shouldMulti = selectedIds.value.includes(key) && selectedIds.value.length > 1
  const dragKeys = shouldMulti ? [...selectedIds.value] : [key]
  // 修饰键选择由 click 阶段统一 toggle，避免 mousedown 先单选后又被移除。
  if (!isToggleGesture && !selectedIds.value.includes(key)) select(key)
  // 启动拖拽追踪
  beginTracking(dragKeys, e.clientX, e.clientY, iconEl)
  // 标记抑制下一次点击（如果触发了拖拽）
  const checkSuppress = () => {
    if (dragState.isDragging) suppressNextClick = true
  }
  setTimeout(checkSuppress, 50)
}

function handleAppClick(appKey: string, e: MouseEvent): void {
  if (suppressNextClick) { suppressNextClick = false; return }
  const key = `app:${appKey}`
  if (e.ctrlKey || e.metaKey) { toggleSelection(key); return }
  if (isSelected(key)) return
  select(key)
}

function handleFileClick(file: FileEntry, e: MouseEvent): void {
  if (suppressNextClick) { suppressNextClick = false; return }
  const key = `file:${file.id}`
  if (e.ctrlKey || e.metaKey) { toggleSelection(key); return }
  if (isSelected(key)) return
  select(key)
}

function handleAppDoubleClick(appKey: string): void {
  suppressNextClick = false
  select(`app:${appKey}`)
  emit('openApp', appKey)
}

function handleFileDoubleClick(file: FileEntry): void {
  suppressNextClick = false
  select(`file:${file.id}`)
  emit('openFile', file)
}

function getFileName(file: FileEntry): string {
  return file.is_folder ? String(file.file_name || '') : formatFileDisplayName(file.file_name, file.format)
}

function handleAppContextMenu(appKey: string, event: MouseEvent) {
  const key = `app:${appKey}`
  if (!isSelected(key)) select(key)
  emit('app-context-menu', appKey, event)
}

function handleFileContextMenu(file: FileEntry, event: MouseEvent) {
  const key = `file:${file.id}`
  if (!isSelected(key)) select(key)
  emit('file-context-menu', file, event)
}

// ═══════════════════════════════════════════════════
// 样式类判定
// ═══════════════════════════════════════════════════

function iconItemClasses(key: string, isFolder?: boolean): Record<string, boolean> {
  return {
    'desktop-icon-item-selected': isSelected(key),
    'desktop-icon-item-dragging': dragState.isDragging && dragState.draggedKeys.includes(key),
    'desktop-icon-item-folder-highlight': !!isFolder && dragState.highlightFolderKey === key,
  }
}
</script>
