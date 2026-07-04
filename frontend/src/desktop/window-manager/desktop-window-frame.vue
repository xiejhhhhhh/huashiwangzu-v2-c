<template>
  <div
    v-if="windowType !== 'background-service'"
    ref="rootEl"
    class="desktop-window"
    :class="windowClasses"
    :style="windowStyle"
    role="dialog"
    :aria-label="title"
    @mousedown.capture="$emit('activate', id)"
  >
    <div
      class="window-titlebar"
      @mousedown.prevent="windowInteraction.startDrag"
      @dblclick="$emit('maximize', id)"
    >
      <div class="window-title-info">
        <AppIcon :icon="icon" :size="16" />
        <span class="window-title">{{ title }}</span>
      </div>
      <div class="window-action-buttons">
        <button v-if="windowType !== 'panel'" class="window-action-btn window-action-minimize" @click.stop="$emit('minimize', id)" title="最小化" aria-label="最小化" />
        <button v-if="windowType !== 'tool' && windowType !== 'background-service'" class="window-action-btn window-action-maximize" @click.stop="$emit('maximize', id)" title="最大化" aria-label="最大化" />
        <button class="window-action-btn window-action-close" @click.stop="requestClose" title="关闭" aria-label="关闭" />
      </div>
    </div>
    <div class="window-content" v-show="contentVisible">
      <div class="window-content-padding">
        <template v-if="currentComponent && !loadError">
          <Suspense>
            <component :is="currentComponent" v-bind="payload || {}" />
            <template #fallback>
              <div class="window-loading">
                <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                <span>正在启动...</span>
              </div>
            </template>
          </Suspense>
        </template>
        <div v-else-if="loadError" class="window-loading">
          <el-icon :size="48" color="#f56c6c"><WarningFilled /></el-icon>
          <p>{{ title }} 启动失败</p>
          <small>{{ loadError }}</small>
        </div>
        <div v-else class="window-loading">
          <el-icon :size="48" color="#909399"><WarningFilled /></el-icon>
          <p>应用未找到或暂不支持此操作</p>
        </div>
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
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { getApp } from '@/desktop/app-registry/app-registry'
import { useWindowInteraction } from './use-window-interaction'
import AppIcon from '@/desktop/components/app-icon.vue'

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
const entered = ref(false)
const closing = ref(false)
const contentVisible = ref(!props.minimized)
let enterFrame = 0
let closeTimer: ReturnType<typeof window.setTimeout> | null = null
let minimizeTimer: ReturnType<typeof window.setTimeout> | null = null

watch(() => props.appKey, () => { loadError.value = '' })
watch(() => props.minimized, (minimized) => {
  if (minimizeTimer) window.clearTimeout(minimizeTimer)
  if (!minimized) {
    contentVisible.value = true
    return
  }
  minimizeTimer = window.setTimeout(() => {
    contentVisible.value = false
  }, 180)
}, { immediate: true })

const currentComponent = computed(() => {
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

const windowStyle = computed(() => ({
  left: `${props.x}px`,
  top: `${props.y}px`,
  width: `${props.width}px`,
  height: `${props.height}px`,
  zIndex: props.zIndex,
}))

const appInfo = computed(() => getApp(props.appKey))
const windowType = computed(() => appInfo.value?.windowType || 'normal')
const resizable = computed(() => appInfo.value?.resizable !== false && windowType.value !== 'fullscreen')
const minWidth = computed(() => appInfo.value?.minWidth ?? 400)
const minHeight = computed(() => appInfo.value?.minHeight ?? 260)

const rootEl = ref<HTMLElement | null>(null)
const windowInteraction = useWindowInteraction(() => ({
  id: props.id, x: props.x, y: props.y, width: props.width, height: props.height, maximized: props.maximized,
  minWidth: minWidth.value, minHeight: minHeight.value, rootEl,
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
  'desktop-window-minimized': props.minimized,
  'desktop-window-closing': closing.value,
  'desktop-window-dragging': windowInteraction.dragging.value,
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
  closeTimer = window.setTimeout(() => emit('close', props.id), 180)
}

onMounted(() => {
  enterFrame = window.requestAnimationFrame(() => {
    entered.value = true
  })
})

onUnmounted(() => {
  if (enterFrame) window.cancelAnimationFrame(enterFrame)
  if (closeTimer) window.clearTimeout(closeTimer)
  if (minimizeTimer) window.clearTimeout(minimizeTimer)
})
</script>

<style scoped>
.desktop-window{opacity:0;transform:translateY(10px) scale(.985);transition:opacity .14s ease,transform .16s cubic-bezier(.2,.8,.2,1),box-shadow .16s ease,border-color .16s ease}.desktop-window:not(.desktop-window-entered),.desktop-window-minimized,.desktop-window-closing,.desktop-window-dragging{will-change:transform,opacity}.desktop-window-entered{opacity:1;transform:translateY(0) scale(1)}.desktop-window-minimized,.desktop-window-closing{opacity:0;transform:translateY(18px) scale(.96);pointer-events:none}.desktop-window-dragging{transition:box-shadow .12s ease,border-color .12s ease}.window-snap-preview{position:absolute;box-sizing:border-box;border:1px solid rgba(125,211,252,.92);background:rgba(14,165,233,.18);box-shadow:inset 0 0 0 1px rgba(255,255,255,.38),0 14px 38px rgba(15,23,42,.22);pointer-events:none;backdrop-filter:blur(4px);transition:left .08s ease,top .08s ease,width .08s ease,height .08s ease,opacity .08s ease}.window-snap-preview-left{border-radius:0 8px 8px 0}.window-snap-preview-right{border-radius:8px 0 0 8px}.window-snap-preview-top{border-radius:0 0 8px 8px}@media (prefers-reduced-motion: reduce){.desktop-window,.window-snap-preview{transition:none}}
.resize-handle{position:absolute;z-index:6}.resize-handle-n,.resize-handle-s{left:10px;right:10px;height:8px;cursor:ns-resize}.resize-handle-n{top:-4px}.resize-handle-s{bottom:-4px}.resize-handle-e,.resize-handle-w{top:10px;bottom:10px;width:8px;cursor:ew-resize}.resize-handle-e{right:-4px}.resize-handle-w{left:-4px}.resize-handle-ne,.resize-handle-sw{width:14px;height:14px;cursor:nesw-resize}.resize-handle-nw,.resize-handle-se{width:14px;height:14px;cursor:nwse-resize}.resize-handle-ne{top:-4px;right:-4px}.resize-handle-nw{top:-4px;left:-4px}.resize-handle-se{right:1px;bottom:1px}.resize-handle-sw{left:-4px;bottom:-4px}.resize-handle-se::after{content:"";position:absolute;right:1px;bottom:1px;width:7px;height:7px;border-right:2px solid rgba(100,116,139,.55);border-bottom:2px solid rgba(100,116,139,.55);border-radius:0 0 3px 0}
</style>
