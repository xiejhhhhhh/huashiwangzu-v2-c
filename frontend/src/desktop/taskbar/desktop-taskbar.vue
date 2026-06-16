<template>
  <div class="桌面任务栏">
    <div class="任务栏开始" @click="$emit('打开启动器')">
      <AppIcon 图标="Start" :size="18" />
      <span class="任务栏开始文字">开始</span>
      <span v-if="启动器打开" class="任务栏启动器指示" />
    </div>
    <div class="任务栏窗口区">
      <div
        v-for="项 in 列表"
        :key="项.id"
        class="TaskbarItem"
        :class="{ 'TaskbarItem-激活': 项.isActive, 'TaskbarItem-最小化': 项.minimized }"
        @click="$emit('切换窗口', 项.id)"
        @mousedown.prevent
      >
        <AppIcon :图标="项.icon" :size="16" />
        <span class="任务栏窗口标题">{{ 项.title }}</span>
      </div>
      <div v-if="!列表.length" class="任务栏空状态">没有打开的窗口</div>
    </div>
    <div class="任务栏右侧">
      <TrayLauncher v-if="托盘应用列表?.length" :应用列表="托盘应用列表" @openApp="(id: string) => $emit('打开托盘应用', id)" />
      <div class="任务栏时钟">{{ 时钟 }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted } from 'vue'
import type { TaskbarItem } from '@/desktop/window-manager/window-types'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import AppIcon from '@/desktop/components/app-icon.vue'

const TrayLauncher = defineAsyncComponent(() => import('./tray-launcher.vue'))
const props = defineProps<{
  任务栏项: TaskbarItem[]
  启动器打开?: boolean
  托盘应用列表?: AppRegistryEntry[]
}>()
defineEmits<{
  (e: '切换窗口', id: string): void
  (e: '打开启动器'): void
  (e: '打开托盘应用', id: string): void
}>()

const 列表 = computed(() => props.任务栏项)

const 时钟 = ref('')
let 时钟定时器: ReturnType<typeof setInterval> | null = null

function 更新时钟() {
  const now = new Date()
  时钟.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

onMounted(() => {
  更新时钟()
  时钟定时器 = setInterval(更新时钟, 30000)
})

onUnmounted(() => {
  if (时钟定时器) clearInterval(时钟定时器)
})
</script>
<style scoped>
.桌面任务栏 {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(14px);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  padding: 0 12px;
  gap: 4px;
  z-index: 10000;
  user-select: none;
}
.任务栏开始 {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px; height: 32px; border-radius: 8px;
  cursor: pointer;
  color: #eff6ff;
}
.任务栏开始:hover { background: rgba(255, 255, 255, 0.14); }
.任务栏开始文字 { font-size: 12px; font-weight: 600; color: #eff6ff; letter-spacing: .2px; }
.任务栏启动器指示 { width: 6px; height: 6px; border-radius: 50%; background: #38bdf8; margin-left: 4px; }
.任务栏窗口区 { flex: 1; display: flex; align-items: center; gap: 2px; margin: 0 4px; overflow-x: auto; }
.TaskbarItem { display: flex; align-items: center; gap: 6px; padding: 0 12px; height: 28px; border-radius: 4px; cursor: pointer; color: #94a3b8; white-space: nowrap; flex-shrink: 0; border: 1px solid transparent; }
.TaskbarItem:hover { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.08); }
.TaskbarItem-激活 { background: rgba(99, 102, 241, 0.15); border-color: rgba(99, 102, 241, 0.2); color: #e2e8f0; }
.TaskbarItem-最小化 { opacity: 0.72; }
.任务栏窗口标题 { font-size: 11px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.任务栏空状态 { font-size: 12px; color: #cbd5e1; padding: 0 8px; }
.任务栏右侧 { display: flex; align-items: center; gap: 6px; padding-left: 8px; border-left: 1px solid rgba(255, 255, 255, 0.1); }
.任务栏时钟 { font-size: 12px; color: #cbd5e1; font-weight: 600; padding: 0 4px; }
</style>
