<template>
  <div
    ref="根元素"
    v-show="!minimized && 窗口类型 !== '后台服务'"
    class="桌面窗口"
    :class="{ '桌面窗口-激活': isActive, '桌面窗口-最大化': maximized, '桌面窗口-全屏': 窗口类型 === '全屏应用' }"
    :style="窗口样式"
    @mousedown.self.prevent="$emit('激活', id)"
  >
    <div
      class="窗口标题栏"
      @mousedown.prevent="窗口交互.开始拖拽"
      @dblclick="$emit('最大化', id)"
    >
      <div class="窗口标题信息">
        <AppIcon :图标="icon" :size="16" />
        <span class="窗口标题">{{ title }}</span>
      </div>
      <button v-if="应用标识 === 'desktop'" class="窗口附加按钮" :class="{ 'is-collapsed': 布局相关.侧栏已折叠, 'is-open': !布局相关.侧栏已折叠 }" :title="布局相关.侧栏已折叠 ? '展开目录导航' : '收起目录导航'" :aria-label="布局相关.侧栏已折叠 ? '展开目录导航' : '收起目录导航'" :aria-checked="!布局相关.侧栏已折叠" role="switch" @click.stop="布局相关.切换侧栏折叠()"><span class="窗口附加按钮轨道"><span class="窗口附加按钮滑块"><span class="窗口附加按钮箭头">{{ 布局相关.侧栏已折叠 ? '›' : '‹' }}</span></span></span></button>
      <div class="窗口操作按钮">
        <button v-if="窗口类型 !== '面板窗口'" class="窗口操作-btn 窗口操作-最小化" @click.stop="$emit('最小化', id)" title="最小化" aria-label="最小化" />
        <button v-if="窗口类型 !== '工具窗口' && 窗口类型 !== '后台服务'" class="窗口操作-btn 窗口操作-最大化" @click.stop="$emit('最大化', id)" title="最大化" aria-label="最大化" />
        <button class="窗口操作-btn 窗口操作-关闭" @click.stop="$emit('关闭', id)" title="关闭" aria-label="关闭" />
      </div>
    </div>
    <div class="窗口内容" v-show="!minimized">
      <div class="窗口内容内边距">
        <template v-if="当前组件 && !加载错误">
          <Suspense>
            <component :is="当前组件" v-bind="负载 || {}" />
            <template #fallback>
              <div class="窗口加载中">
                <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                <span>正在启动...</span>
              </div>
            </template>
          </Suspense>
        </template>
        <div v-else-if="加载错误" class="窗口加载中">
          <el-icon :size="48" color="#f56c6c"><WarningFilled /></el-icon>
          <p>{{ title }} 启动失败</p>
          <small>{{ 加载错误 }}</small>
        </div>
        <div v-else class="窗口加载中">
          <el-icon :size="48" color="#909399"><WarningFilled /></el-icon>
          <p>应用未找到或暂不支持此操作</p>
        </div>
      </div>
    </div>
    <div v-for="方向 in 窗口交互.缩放方向列表" v-if="是否可调整大小 && !maximized" :key="方向" :class="['resize-handle', `resize-handle-${方向}`]" @mousedown.stop="窗口交互.开始缩放(方向, $event)" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, defineAsyncComponent, watch } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { getApp } from '@/desktop/app-registry/app-registry'
import { use窗口交互 } from './use-window-interaction'
import { use桌面布局状态 } from '@/desktop/window-manager/use-desktop-layout-state'
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
  应用标识: string
  负载?: Record<string, unknown>
}>()

const emit = defineEmits<{
  (e: '激活', id: string): void
  (e: '关闭', id: string): void
  (e: '最小化', id: string): void
  (e: '最大化', id: string): void
  (e: '更新位置', id: string, x: number, y: number): void
  (e: '更新几何', id: string, x: number, y: number, w: number, h: number): void
}>()

const 加载错误 = ref('')

watch(() => props.应用标识, () => { 加载错误.value = '' })

const 当前组件 = computed(() => {
  const 应用 = getApp(props.应用标识)
  if (!应用) return null
  return defineAsyncComponent({
    loader: 应用.entryComponent,
    onError(error, _retry, fail) {
      加载错误.value = error?.message || '应用入口组件加载失败'
      console.error(`[DesktopApp] ${props.应用标识} failed to load`, error)
      fail()
    },
  })
})

const 窗口样式 = computed(() => ({
  left: `${props.x}px`,
  top: `${props.y}px`,
  width: `${props.width}px`,
  height: `${props.height}px`,
  zIndex: props.zIndex,
}))

const 应用信息 = computed(() => getApp(props.应用标识))
const 窗口类型 = computed(() => 应用信息.value?.windowType || '普通窗口')
const 是否可调整大小 = computed(() => 应用信息.value?.resizable !== false && 窗口类型.value !== '全屏应用')
const 最小宽 = computed(() => 应用信息.value?.minWidth ?? 400)
const 最小高 = computed(() => 应用信息.value?.minHeight ?? 260)
const 布局相关 = use桌面布局状态()

const 根元素 = ref<HTMLElement | null>(null)
const 窗口交互 = use窗口交互(() => ({
  id: props.id, x: props.x, y: props.y, width: props.width, height: props.height, maximized: props.maximized,
  minWidth: 最小宽.value, minHeight: 最小高.value, 根元素,
  激活: (id) => emit('激活', id), 更新位置: (id, x, y) => emit('更新位置', id, x, y),
  更新几何: (id, x, y, w, h) => emit('更新几何', id, x, y, w, h),
}))
</script>

<style scoped>
.窗口附加按钮{position:absolute;right:12px;top:50%;transform:translateY(-50%);padding:0;border:none;background:transparent;cursor:pointer}.窗口附加按钮轨道{width:42px;height:24px;padding:3px;border-radius:999px;display:flex;align-items:center;background:linear-gradient(180deg,#94a3b8,#64748b);box-shadow:inset 0 0 0 1px rgba(71,85,105,.28),0 6px 12px rgba(15,23,42,.12);transition:background .22s ease,box-shadow .22s ease}.窗口附加按钮滑块{width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#fff;color:#475569;box-shadow:0 2px 6px rgba(15,23,42,.22);transform:translateX(0);transition:transform .22s ease,color .22s ease}.窗口附加按钮箭头{font-size:16px;line-height:1;font-weight:800}.窗口附加按钮.is-open .窗口附加按钮轨道{background:linear-gradient(180deg,#60a5fa,#2563eb);box-shadow:inset 0 0 0 1px rgba(37,99,235,.3),0 6px 12px rgba(37,99,235,.18)}.窗口附加按钮.is-open .窗口附加按钮滑块{transform:translateX(18px);color:#2563eb}.窗口附加按钮:focus-visible{outline:2px solid #2563eb;outline-offset:3px}
.resize-handle{position:absolute;z-index:6}.resize-handle-n,.resize-handle-s{left:10px;right:10px;height:8px;cursor:ns-resize}.resize-handle-n{top:-4px}.resize-handle-s{bottom:-4px}.resize-handle-e,.resize-handle-w{top:10px;bottom:10px;width:8px;cursor:ew-resize}.resize-handle-e{right:-4px}.resize-handle-w{left:-4px}.resize-handle-ne,.resize-handle-sw{width:14px;height:14px;cursor:nesw-resize}.resize-handle-nw,.resize-handle-se{width:14px;height:14px;cursor:nwse-resize}.resize-handle-ne{top:-4px;right:-4px}.resize-handle-nw{top:-4px;left:-4px}.resize-handle-se{right:1px;bottom:1px}.resize-handle-sw{left:-4px;bottom:-4px}.resize-handle-se::after{content:"";position:absolute;right:1px;bottom:1px;width:7px;height:7px;border-right:2px solid rgba(100,116,139,.55);border-bottom:2px solid rgba(100,116,139,.55);border-radius:0 0 3px 0}
</style>
