<template>
  <div
    ref="rootEl"
    v-show="!minimized && windowType !== 'background-service'"
    class="desktop-window"
    :class="{ 'desktop-window-active': isActive, 'desktop-window-maximized': maximized, 'desktop-window-fullscreen': windowType === 'fullscreen' }"
    :style="windowStyle"
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
        <button class="window-action-btn window-action-close" @click.stop="$emit('close', id)" title="关闭" aria-label="关闭" />
      </div>
    </div>
    <div class="window-content" v-show="!minimized">
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
</template>

<script setup lang="ts">
import { computed, ref, defineAsyncComponent, watch } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { getApp } from '@/desktop/app-registry/app-registry'
import { useWindowInteraction } from './use-window-interaction'
import AppIcon from '@/desktop/components/app-icon.vue'

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
  (e: 'maximize', id: string): void
  (e: 'update-position', id: string, x: number, y: number): void
  (e: 'update-geometry', id: string, x: number, y: number, w: number, h: number): void
}>()

const loadError = ref('')

watch(() => props.appKey, () => { loadError.value = '' })

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
}))
</script>

<style scoped>
.resize-handle{position:absolute;z-index:6}.resize-handle-n,.resize-handle-s{left:10px;right:10px;height:8px;cursor:ns-resize}.resize-handle-n{top:-4px}.resize-handle-s{bottom:-4px}.resize-handle-e,.resize-handle-w{top:10px;bottom:10px;width:8px;cursor:ew-resize}.resize-handle-e{right:-4px}.resize-handle-w{left:-4px}.resize-handle-ne,.resize-handle-sw{width:14px;height:14px;cursor:nesw-resize}.resize-handle-nw,.resize-handle-se{width:14px;height:14px;cursor:nwse-resize}.resize-handle-ne{top:-4px;right:-4px}.resize-handle-nw{top:-4px;left:-4px}.resize-handle-se{right:1px;bottom:1px}.resize-handle-sw{left:-4px;bottom:-4px}.resize-handle-se::after{content:"";position:absolute;right:1px;bottom:1px;width:7px;height:7px;border-right:2px solid rgba(100,116,139,.55);border-bottom:2px solid rgba(100,116,139,.55);border-radius:0 0 3px 0}
</style>
