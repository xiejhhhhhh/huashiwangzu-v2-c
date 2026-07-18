<template>
  <div
    v-if="windowType !== 'background-service'"
    ref="rootEl"
    class="desktop-window glass-window"
    :class="[windowClasses, { 'desktop-window-finder': isFinderWindow }]"
    :style="windowStyle"
    :data-window-id="id"
    :data-accepts-drop="appKey === 'desktop' ? 'true' : undefined"
    role="dialog"
    :aria-label="title"
    @mousedown.capture="$emit('activate', id)"
  >
    <div
      class="window-titlebar"
      @mousedown="handleTitlebarMouseDown"
      @dblclick="$emit('maximize', id)"
    >
      <div class="window-title-info">
        <AppIcon :icon="icon" :app-key="appKey" :size="16" />
        <span class="window-title">{{ title }}</span>
      </div>
      <div class="window-action-buttons">
        <button class="window-action-btn window-action-close" @click.stop="requestClose" title="关闭" aria-label="关闭" />
        <button v-if="windowType !== 'panel'" class="window-action-btn window-action-minimize" @click.stop="handleMinimize" title="最小化" aria-label="最小化" />
        <button v-if="windowType !== 'tool' && windowType !== 'background-service'" class="window-action-btn window-action-maximize" @click.stop="$emit('maximize', id)" title="缩放" aria-label="缩放" />
      </div>
    </div>
    <div v-if="hasMountedContent" class="window-content" v-show="contentVisible">
      <div class="window-content-padding">
        <template v-if="currentComponent && !loadError">
          <Suspense>
            <component :is="currentComponent" v-bind="{ ...(payload || {}), windowId: id }" />
            <template #fallback>
              <AsyncPaneState :title="`正在启动${title}`" />
            </template>
          </Suspense>
        </template>
        <AsyncPaneState v-else-if="loadError" :title="`${title}启动失败`" :error="loadError" @retry="retryLoad" />
        <AsyncPaneState v-else title="应用不可用" description="应用未找到或暂不支持此操作。" />
      </div>
    </div>
    <div v-for="direction in windowInteraction.resizeDirections" v-if="resizable && !maximized" :key="direction" :class="['resize-handle', `resize-handle-${direction}`]" @mousedown.stop="windowInteraction.startResize(direction, $event)" />
  </div>
  <div
    v-if="snapPreview"
    class="window-snap-preview"
    :class="`window-snap-preview-${snapPreview.kind}`"
    :style="snapPreviewStyle"
    aria-hidden="true"
  />
</template>
<script setup lang="ts">
import { computed, ref, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { getApp } from '@/desktop/app-registry/app-registry'
import { useWindowInteraction } from './use-window-interaction'
import { desktopConfig } from '@/desktop/config/desktop-preferences'
import AppIcon from '@/desktop/components/app-icon.vue'
import AsyncPaneState from '@/shared/components/async-pane-state.vue'

type WindowGeometry = { x: number; y: number; width: number; height: number }

const props = defineProps<{
  id: string
  title: string
  icon: string
  x: number
  y: number
  width: number
  height: number
  zIndex: number
  minimized: boolean
  maximized: boolean
  isActive: boolean
  appKey: string
  payload?: Record<string, unknown>
  preMaximizeState?: WindowGeometry
  animationOrigin?: { x: number; y: number; width: number; height: number }
}>()

const emit = defineEmits<{
  (e: 'activate', id: string): void
  (e: 'close', id: string): void
  (e: 'minimize', id: string): void
  (e: 'maximize', id: string, restoreState?: WindowGeometry): void
  (e: 'update-position', id: string, x: number, y: number): void
  (e: 'update-geometry', id: string, x: number, y: number, w: number, h: number): void
}>()

const loadError = ref('')
const loadAttempt = ref(0)
const entered = ref(false)
const closing = ref(false)
const minimizing = ref(false)
const restoring = ref(false)
const openingFromOrigin = ref(false)
const contentVisible = ref(!props.minimized)
const hasMountedContent = ref(!props.minimized)
let enterFrame = 0
let closeTimer: ReturnType<typeof window.setTimeout> | null = null
let minimizeTimer: ReturnType<typeof window.setTimeout> | null = null
let restoreTimer: ReturnType<typeof window.setTimeout> | null = null

const animDuration = computed(() => desktopConfig.windowAnimationDuration)

watch(() => props.appKey, () => { loadError.value = '' })

// 最小化/还原动画逻辑
watch(() => props.minimized, (minimized, oldMinimized) => {
  if (minimizeTimer) window.clearTimeout(minimizeTimer)
  if (restoreTimer) window.clearTimeout(restoreTimer)

  if (minimized && !oldMinimized) {
    // 正在最小化 → 播放最小化动画
    minimizing.value = true
    applyMinimizeTargetVars()
    minimizeTimer = window.setTimeout(() => {
      contentVisible.value = false
      minimizing.value = false
    }, animDuration.value)
  } else if (!minimized && oldMinimized) {
    // 从最小化还原 → 播放还原动画
    contentVisible.value = true
    hasMountedContent.value = true
    restoring.value = true
    applyMinimizeTargetVars()
    restoreTimer = window.setTimeout(() => {
      restoring.value = false
    }, animDuration.value)
  } else {
    contentVisible.value = !minimized
    if (!minimized) hasMountedContent.value = true
  }
}, { immediate: true })

function getTaskbarButtonRect(): { x: number; y: number } | null {
  const btn = document.querySelector(`[data-dock-app-key="${props.appKey}"]`) as HTMLElement | null
  if (btn) {
    const rect = btn.getBoundingClientRect()
    const parent = rootEl.value?.parentElement
    const parentRect = parent?.getBoundingClientRect()
    return {
      x: rect.left - (parentRect?.left ?? 0) + rect.width / 2,
      y: rect.top - (parentRect?.top ?? 0) + rect.height / 2,
    }
  }
  // 没有应用图标时退回到底部中央。
  const parent = rootEl.value?.parentElement
  return {
    x: (parent?.clientWidth ?? window.innerWidth) / 2,
    y: (parent?.clientHeight ?? window.innerHeight) - 24,
  }
}

function applyMinimizeTargetVars() {
  if (!rootEl.value) return
  const target = getTaskbarButtonRect()
  if (target) {
    const windowCenterX = props.x + props.width / 2
    const windowCenterY = props.y + props.height / 2
    rootEl.value.style.setProperty('--minimize-target-x', `${target.x - windowCenterX}px`)
    rootEl.value.style.setProperty('--minimize-target-y', `${target.y - windowCenterY}px`)
  }
}

function handleMinimize() {
  emit('minimize', props.id)
}

function handleTitlebarMouseDown(event: MouseEvent) {
  if ((event.target as HTMLElement).closest('.window-action-buttons')) return
  event.preventDefault()
  windowInteraction.startDrag(event)
}

const currentComponent = computed(() => {
  loadAttempt.value
  const app = getApp(props.appKey)
  if (!app) return null
  return defineAsyncComponent({
    loader: app.entryComponent,
    onError(error, _retry, fail) {
      loadError.value = error?.message || '应用入口组件加载失败'
      console.error(`[DesktopApp] ${props.appKey} failed to load`, error)
      fail()
    },
  })
})

function retryLoad() {
  loadError.value = ''
  loadAttempt.value += 1
}

const windowStyle = computed(() => {
  const style: Record<string, string> = {
    left: `${props.x}px`,
    top: `${props.y}px`,
    width: `${props.width}px`,
    height: `${props.height}px`,
    zIndex: String(props.zIndex),
    '--window-anim-duration': `${animDuration.value}ms`,
  }
  // 打开动画来源坐标
  if (props.animationOrigin && !entered.value) {
    const origin = props.animationOrigin
    const scaleX = origin.width / props.width
    const scaleY = origin.height / props.height
    const translateX = origin.x - props.x + (origin.width - props.width) / 2
    const translateY = origin.y - props.y + (origin.height - props.height) / 2
    style['--origin-translate-x'] = `${translateX}px`
    style['--origin-translate-y'] = `${translateY}px`
    style['--origin-scale-x'] = String(scaleX.toFixed(4))
    style['--origin-scale-y'] = String(scaleY.toFixed(4))
  }
  return style
})

const appInfo = computed(() => getApp(props.appKey))
const isFinderWindow = computed(() => props.appKey === 'files' || props.appKey === 'desktop')
const windowType = computed(() => appInfo.value?.windowType || 'normal')
const resizable = computed(() => appInfo.value?.resizable !== false && windowType.value !== 'fullscreen')
const minWidth = computed(() => appInfo.value?.minWidth ?? 400)
const minHeight = computed(() => appInfo.value?.minHeight ?? 260)
const preMaximizeState = computed(() => props.preMaximizeState)

const rootEl = ref<HTMLElement | null>(null)
const windowInteraction = useWindowInteraction(() => ({
  id: props.id, x: props.x, y: props.y, width: props.width, height: props.height, maximized: props.maximized,
  minWidth: minWidth.value, minHeight: minHeight.value, rootEl,
  preMaximizeState: preMaximizeState.value,
  activate: (id) => emit('activate', id), updatePosition: (id, x, y) => emit('update-position', id, x, y),
  updateGeometry: (id, x, y, w, h) => emit('update-geometry', id, x, y, w, h),
  maximize: (id, restoreState) => emit('maximize', id, restoreState),
}))
const snapPreview = windowInteraction.snapPreview
const windowClasses = computed(() => ({
  'desktop-window-active': props.isActive,
  'desktop-window-maximized': props.maximized,
  'desktop-window-fullscreen': windowType.value === 'fullscreen',
  'desktop-window-entered': entered.value,
  'desktop-window-minimized': props.minimized && !minimizing.value && !restoring.value,
  'desktop-window-minimizing': minimizing.value,
  'desktop-window-restoring': restoring.value,
  'desktop-window-closing': closing.value,
  'desktop-window-dragging': windowInteraction.dragging.value,
  'desktop-window-opening-from-origin': openingFromOrigin.value,
  'desktop-window-maximized-transition': props.maximized || entered.value,
}))
const snapPreviewStyle = computed(() => {
  const preview = snapPreview.value
  if (!preview) return {}
  const zIndex = Number.isFinite(props.zIndex) ? props.zIndex + 1 : 1
  return {
    left: `${preview.x}px`,
    top: `${preview.y}px`,
    width: `${preview.width}px`,
    height: `${preview.height}px`,
    zIndex,
  }
})

function requestClose() {
  if (closing.value) return
  closing.value = true
  closeTimer = window.setTimeout(() => emit('close', props.id), animDuration.value)
}

onMounted(() => {
  if (props.animationOrigin) {
    // 从来源坐标展开的动画
    openingFromOrigin.value = true
    enterFrame = window.requestAnimationFrame(() => {
      entered.value = true
      setTimeout(() => { openingFromOrigin.value = false }, animDuration.value)
    })
  } else {
    // 通用淡入动画
    enterFrame = window.requestAnimationFrame(() => {
      entered.value = true
    })
  }
})

onUnmounted(() => {
  if (enterFrame) window.cancelAnimationFrame(enterFrame)
  if (closeTimer) window.clearTimeout(closeTimer)
  if (minimizeTimer) window.clearTimeout(minimizeTimer)
  if (restoreTimer) window.clearTimeout(restoreTimer)
})
</script>

<style scoped>
/* ═══ 基础窗口状态 ═══ */
.desktop-window {
  position: absolute;
  opacity: 0;
  transform: scale(0.95);
  will-change: transform, opacity;
  transition:
    opacity var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    transform var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    box-shadow 0.16s ease,
    border-color 0.16s ease;
}

/* Finder / 访达：更接近系统标题栏（隐藏应用图标，仅保留居中标题） */
.desktop-window-finder :deep(.window-title-info .app-icon) {
  display: none;
}
.desktop-window-finder :deep(.window-title) {
  font-weight: 600;
  letter-spacing: -0.01em;
}
.desktop-window-finder :deep(.window-titlebar) {
  height: 40px;
}
.desktop-window-finder :deep(.window-content) {
  background: transparent;
}

/* ═══ 打开动画 - 通用（从中心淡入） ═══ */
.desktop-window-entered {
  opacity: 1;
  transform: scale(1);
}

/* ═══ 打开动画 - 从来源坐标展开 ═══ */
.desktop-window-opening-from-origin:not(.desktop-window-entered) {
  opacity: 0;
  transform: translate(var(--origin-translate-x, 0), var(--origin-translate-y, 0))
             scale(var(--origin-scale-x, 0.5), var(--origin-scale-y, 0.5));
}
.desktop-window-opening-from-origin.desktop-window-entered {
  opacity: 1;
  transform: translate(0, 0) scale(1);
}

/* ═══ 关闭动画 ═══ */
.desktop-window-closing {
  opacity: 0;
  transform: scale(0.92);
  pointer-events: none;
  transition:
    opacity var(--window-anim-duration, 200ms) cubic-bezier(0.5, 0, 0.75, 0),
    transform var(--window-anim-duration, 200ms) cubic-bezier(0.5, 0, 0.75, 0);
}

/* ═══ 最小化动画 - genie 近似（飞入 Dock + 纵向压缩） ═══ */
.desktop-window-minimizing {
  opacity: 0;
  transform: translate(var(--minimize-target-x, 0), var(--minimize-target-y, 0)) scale(0.12, 0.04);
  filter: blur(1.2px);
  pointer-events: none;
  transform-origin: 50% 100%;
  transition:
    opacity var(--window-anim-duration, 280ms) cubic-bezier(0.55, 0.05, 0.8, 0.15),
    transform var(--window-anim-duration, 280ms) cubic-bezier(0.55, 0.05, 0.8, 0.15),
    filter var(--window-anim-duration, 280ms) ease;
}

/* ═══ 从 Dock 还原动画 ═══ */
.desktop-window-restoring {
  animation: window-restore-keyframes var(--window-anim-duration, 280ms) cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes window-restore-keyframes {
  from {
    opacity: 0;
    transform: translate(var(--minimize-target-x, 0), var(--minimize-target-y, 0)) scale(0.12, 0.04);
    filter: blur(1.2px);
  }
  70% {
    opacity: 1;
    filter: blur(0);
  }
  to {
    opacity: 1;
    transform: translate(0, 0) scale(1);
    filter: none;
  }
}

/* ═══ 已最小化（动画结束后的静态状态） ═══ */
.desktop-window-minimized {
  opacity: 0;
  transform: translate(var(--minimize-target-x, 0), var(--minimize-target-y, 0)) scale(0.12, 0.04);
  pointer-events: none;
}

/* ═══ 最大化/还原过渡 ═══ */
.desktop-window-maximized-transition {
  transition:
    left var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    top var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    width var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    height var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    border-radius var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    opacity var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    transform var(--window-anim-duration, 200ms) cubic-bezier(0.16, 1, 0.3, 1),
    box-shadow 0.16s ease,
    border-color 0.16s ease;
}

.desktop-window-maximized {
  border-radius: var(--window-maximized-radius) !important;
}

/* ═══ 拖拽时禁用过渡 ═══ */
.desktop-window-dragging {
  transition: box-shadow 0.12s ease, border-color 0.12s ease !important;
}

/* ═══ 贴靠预览框 ═══ */
.window-snap-preview {
  position: absolute;
  box-sizing: border-box;
  border: 1px solid rgba(125, 211, 252, 0.92);
  background: rgba(14, 165, 233, 0.18);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.38), 0 14px 38px rgba(15, 23, 42, 0.22);
  pointer-events: none;
  backdrop-filter: blur(4px);
  transition:
    left 0.08s ease,
    top 0.08s ease,
    width 0.08s ease,
    height 0.08s ease,
    opacity 0.08s ease;
}
.window-snap-preview-top { border-radius: 0 0 8px 8px; }

/* ═══ 缩放手柄 ═══ */
.resize-handle { position: absolute; z-index: 6; }
.resize-handle-n, .resize-handle-s { left: 10px; right: 10px; height: 8px; cursor: ns-resize; }
.resize-handle-n { top: -4px; }
.resize-handle-s { bottom: -4px; }
.resize-handle-e, .resize-handle-w { top: 10px; bottom: 10px; width: 8px; cursor: ew-resize; }
.resize-handle-e { right: -4px; }
.resize-handle-w { left: -4px; }
.resize-handle-ne, .resize-handle-sw { width: 14px; height: 14px; cursor: nesw-resize; }
.resize-handle-nw, .resize-handle-se { width: 14px; height: 14px; cursor: nwse-resize; }
.resize-handle-ne { top: -4px; right: -4px; }
.resize-handle-nw { top: -4px; left: -4px; }
.resize-handle-se { right: 1px; bottom: 1px; }
.resize-handle-sw { left: -4px; bottom: -4px; }
.resize-handle-se::after {
  content: "";
  position: absolute;
  right: 1px;
  bottom: 1px;
  width: 7px;
  height: 7px;
  border-right: 2px solid rgba(100, 116, 139, 0.55);
  border-bottom: 2px solid rgba(100, 116, 139, 0.55);
  border-radius: 0 0 3px 0;
}

/* ═══ 无障碍：减弱动画偏好 ═══ */
@media (prefers-reduced-motion: reduce) {
  .desktop-window,
  .desktop-window-maximized-transition,
  .window-snap-preview {
    transition: none !important;
    animation: none !important;
  }
}
</style>
