<template>
  <div class="desktop-taskbar">
    <div class="taskbar-start" @click="$emit('openLauncher')">
      <AppIcon icon="Start" :size="18" />
      <span class="taskbar-start-label">开始</span>
      <span v-if="launcherOpen" class="taskbar-launcher-indicator" />
    </div>
    <div class="taskbar-window-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="taskbar-item"
        :class="{ 'taskbar-item-active': item.isActive, 'taskbar-item-minimized': item.minimized }"
        @click="$emit('switchWindow', item.id)"
        @mousedown.prevent
      >
        <AppIcon :icon="item.icon" :size="16" />
        <span class="taskbar-window-title">{{ item.title }}</span>
      </div>
      <div v-if="!items.length" class="taskbar-empty">没有打开的窗口</div>
    </div>
    <div class="taskbar-right">
      <TrayLauncher v-if="trayApps?.length" :app-list="trayApps" @openApp="(id: string) => $emit('openTrayApp', id)" />
      <div class="taskbar-clock">{{ clockText }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent, onMounted, onUnmounted } from 'vue'
import type { TaskbarItem } from '@/desktop/window-manager/window-types'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import AppIcon from '@/desktop/components/app-icon.vue'

const TrayLauncher = defineAsyncComponent(() => import('./tray-launcher.vue'))
const props = defineProps<{
  items: TaskbarItem[]
  launcherOpen?: boolean
  trayApps?: AppRegistryEntry[]
}>()
defineEmits<{
  (e: 'switchWindow', id: string): void
  (e: 'openLauncher'): void
  (e: 'openTrayApp', id: string): void
}>()

const clockText = ref('')
let clockTimer: ReturnType<typeof setInterval> | null = null

function updateClock() {
  const now = new Date()
  clockText.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 30000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
})
</script>
<style scoped>
.desktop-taskbar {
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
.taskbar-start {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px; height: 32px; border-radius: 8px;
  cursor: pointer;
  color: #eff6ff;
}
.taskbar-start:hover { background: rgba(255, 255, 255, 0.14); }
.taskbar-start-label { font-size: 12px; font-weight: 600; color: #eff6ff; letter-spacing: .2px; }
.taskbar-launcher-indicator { width: 6px; height: 6px; border-radius: 50%; background: #38bdf8; margin-left: 4px; }
.taskbar-window-list { flex: 1; display: flex; align-items: center; gap: 2px; margin: 0 4px; overflow-x: auto; }
.taskbar-item { display: flex; align-items: center; gap: 6px; padding: 0 12px; height: 28px; border-radius: 4px; cursor: pointer; color: #94a3b8; white-space: nowrap; flex-shrink: 0; border: 1px solid transparent; }
.taskbar-item:hover { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.08); }
.taskbar-item-active { background: rgba(99, 102, 241, 0.15); border-color: rgba(99, 102, 241, 0.2); color: #e2e8f0; }
.taskbar-item-minimized { opacity: 0.72; }
.taskbar-window-title { font-size: 11px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.taskbar-empty { font-size: 12px; color: #cbd5e1; padding: 0 8px; }
.taskbar-right { display: flex; align-items: center; gap: 6px; padding-left: 8px; border-left: 1px solid rgba(255, 255, 255, 0.1); }
.taskbar-clock { font-size: 12px; color: #cbd5e1; font-weight: 600; padding: 0 4px; }
</style>
