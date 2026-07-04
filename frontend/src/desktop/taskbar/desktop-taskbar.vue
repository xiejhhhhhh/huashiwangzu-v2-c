<template>
  <div class="desktop-taskbar">
    <div
      class="taskbar-start"
      role="button"
      tabindex="0"
      :aria-pressed="launcherOpen ? 'true' : 'false'"
      @click="$emit('openLauncher')"
      @keydown.enter.prevent="$emit('openLauncher')"
      @keydown.space.prevent="$emit('openLauncher')"
    >
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
        role="button"
        tabindex="0"
        :aria-label="`切换窗口：${item.title}`"
        :aria-pressed="item.isActive ? 'true' : 'false'"
        @click="$emit('switchWindow', item.id)"
        @keydown.enter.prevent="$emit('switchWindow', item.id)"
        @keydown.space.prevent="$emit('switchWindow', item.id)"
        @mousedown.prevent
      >
        <AppIcon :icon="item.icon" :size="16" />
        <span class="taskbar-window-title">{{ item.title }}</span>
      </div>
      <div v-if="!items.length" class="taskbar-empty">没有打开的窗口</div>
    </div>
    <div class="taskbar-right">
      <TaskbarNotifications @open-app="(id: string, payload?: Record<string, unknown>) => $emit('openTrayApp', id, payload)" />
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
const TaskbarNotifications = defineAsyncComponent(() => import('./taskbar-notifications.vue'))
const props = defineProps<{
  items: TaskbarItem[]
  launcherOpen?: boolean
  trayApps?: AppRegistryEntry[]
}>()
defineEmits<{
  (e: 'switchWindow', id: string): void
  (e: 'openLauncher'): void
  (e: 'openTrayApp', id: string, payload?: Record<string, unknown>): void
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
  background: rgba(15, 23, 42, 0.46);
  backdrop-filter: blur(20px) saturate(1.12);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 -10px 34px rgba(15, 23, 42, 0.24);
  display: flex;
  align-items: center;
  padding: 0 12px;
  gap: 4px;
  z-index: 10000;
  user-select: none;
}
.taskbar-start {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px; height: 32px; border-radius: 8px;
  cursor: pointer;
  color: #eff6ff;
  border: 1px solid transparent;
  transition: background .16s ease, border-color .16s ease, box-shadow .16s ease, transform .16s ease;
}
.taskbar-start:hover,
.taskbar-start:focus-visible {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.2);
  transform: translateY(-1px);
}
.taskbar-start:focus-visible {
  outline: 2px solid rgba(191, 219, 254, .9);
  outline-offset: 2px;
}
.taskbar-start-label { font-size: 12px; font-weight: 700; color: #eff6ff; }
.taskbar-launcher-indicator { width: 6px; height: 6px; border-radius: 50%; background: #38bdf8; margin-left: 4px; box-shadow: 0 0 12px rgba(56, 189, 248, .9); }
.taskbar-window-list { flex: 1; display: flex; align-items: center; gap: 2px; margin: 0 4px; overflow-x: auto; }
.taskbar-item { position: relative; display: flex; align-items: center; gap: 6px; padding: 0 12px; height: 30px; border-radius: 7px; cursor: pointer; color: #cbd5e1; white-space: nowrap; flex-shrink: 0; border: 1px solid transparent; transition: background .16s ease, border-color .16s ease, color .16s ease, opacity .16s ease, transform .16s ease; }
.taskbar-item::after { content: ''; position: absolute; left: 12px; right: 12px; bottom: 3px; height: 2px; border-radius: 999px; background: transparent; }
.taskbar-item:hover,
.taskbar-item:focus-visible { background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.12); transform: translateY(-1px); }
.taskbar-item:focus-visible { outline: 2px solid rgba(191, 219, 254, .9); outline-offset: 2px; }
.taskbar-item-active { background: rgba(59, 130, 246, 0.18); border-color: rgba(147, 197, 253, 0.3); color: #f8fafc; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06); }
.taskbar-item-active::after { background: #60a5fa; box-shadow: 0 0 10px rgba(96, 165, 250, .72); }
.taskbar-item-minimized { opacity: 0.66; }
.taskbar-item-minimized::after { background: rgba(203, 213, 225, 0.42); }
.taskbar-window-title { font-size: 11px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.taskbar-empty { font-size: 12px; color: #cbd5e1; padding: 0 8px; }
.taskbar-right { display: flex; align-items: center; gap: 6px; padding-left: 8px; border-left: 1px solid rgba(255, 255, 255, 0.1); }
.taskbar-clock { font-size: 12px; color: #cbd5e1; font-weight: 600; padding: 0 4px; }
</style>
