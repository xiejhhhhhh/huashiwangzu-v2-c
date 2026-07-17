<template>
  <div class="desktop-taskbar">
    <div
      class="taskbar-start"
      role="button"
      tabindex="0"
      aria-label="打开启动器"
      title="启动器"
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
        @mouseenter="onItemMouseEnter($event, item)"
        @mouseleave="onItemMouseLeave"
      >
        <AppIcon :icon="item.icon" :size="16" />
        <span class="taskbar-window-title">{{ item.title }}</span>
        <!-- 进度条 -->
        <div v-if="getProgress(item.appKey)" class="taskbar-progress-bar">
          <div
            class="taskbar-progress-fill"
            :class="{ 'taskbar-progress-indeterminate': getProgress(item.appKey)?.progress === -1 }"
            :style="progressStyle(item.appKey)"
          />
        </div>
      </div>
      <div v-if="!items.length" class="taskbar-empty">没有打开的窗口</div>
    </div>
    <div class="taskbar-right">
      <TaskbarNotifications @open-app="(id: string, payload?: Record<string, unknown>) => $emit('openTrayApp', id, payload)" />
      <TrayLauncher v-if="trayApps?.length" :app-list="trayApps" @openApp="(id: string) => $emit('openTrayApp', id)" />
      <!-- 时钟升级版 -->
      <div
        class="taskbar-clock"
        @mouseenter="clockHover = true"
        @mouseleave="clockHover = false"
      >
        <span class="clock-main">{{ clockTime }}</span>
        <span class="clock-date">{{ clockDate }}</span>
        <!-- 时钟悬浮面板 -->
        <Transition name="clock-panel-fade">
          <div v-if="clockHover" class="clock-panel">
            <div class="clock-panel-time">{{ clockFull }}</div>
            <div class="clock-panel-date">{{ clockFullDate }}</div>
            <div class="clock-panel-weekday">{{ clockWeekday }}</div>
          </div>
        </Transition>
      </div>
      <!-- 显示桌面按钮 -->
      <div
        class="taskbar-show-desktop"
        role="button"
        tabindex="0"
        title="显示桌面"
        @click="onShowDesktop"
        @keydown.enter.prevent="onShowDesktop"
        @keydown.space.prevent="onShowDesktop"
      >
        <div class="show-desktop-line" />
      </div>
    </div>
    <!-- 窗口预览组件 -->
    <TaskbarWindowPreview
      :visible="previewVisible"
      :window-id="previewWindowId"
      :window-title="previewWindowTitle"
      :window-icon="previewWindowIcon"
      :anchor-rect="previewAnchorRect"
      @close-window="onPreviewClose"
      @keep-alive="onPreviewKeepAlive"
      @dismiss="onPreviewDismiss"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent, onMounted, onUnmounted } from 'vue'
import type { TaskbarItem } from '@/desktop/window-manager/window-types'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import AppIcon from '@/desktop/components/app-icon.vue'
import { activeProgress } from '@/desktop/feedback/desktop-feedback'
import TaskbarWindowPreview from './taskbar-window-preview.vue'

const TrayLauncher = defineAsyncComponent(() => import('./tray-launcher.vue'))
const TaskbarNotifications = defineAsyncComponent(() => import('./taskbar-notifications.vue'))

const props = defineProps<{
  items: TaskbarItem[]
  launcherOpen?: boolean
  trayApps?: AppRegistryEntry[]
}>()

const emit = defineEmits<{
  (e: 'switchWindow', id: string): void
  (e: 'openLauncher'): void
  (e: 'openTrayApp', id: string, payload?: Record<string, unknown>): void
  (e: 'showDesktop'): void
  (e: 'closeWindow', id: string): void
}>()

// ═══════════════════════════════════════════════════
// 时钟系统
// ═══════════════════════════════════════════════════
const clockTime = ref('')
const clockDate = ref('')
const clockFull = ref('')
const clockFullDate = ref('')
const clockWeekday = ref('')
const clockHover = ref(false)
let clockTimer: ReturnType<typeof setInterval> | null = null

const WEEKDAYS = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']

function updateClock() {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  clockTime.value = `${h}:${m}`
  clockDate.value = `${now.getMonth() + 1}/${now.getDate()}`
  clockFull.value = `${h}:${m}:${s}`
  clockFullDate.value = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
  clockWeekday.value = WEEKDAYS[now.getDay()]
}

// ═══════════════════════════════════════════════════
// 进度条
// ═══════════════════════════════════════════════════
function getProgress(appKey?: string) {
  if (!appKey) return null
  return activeProgress.value.get(appKey) || null
}

function progressStyle(appKey?: string) {
  const entry = getProgress(appKey)
  if (!entry) return {}
  if (entry.progress === -1) return { background: entry.color || '#3b82f6' }
  return {
    width: `${Math.min(100, entry.progress * 100)}%`,
    background: entry.color || '#3b82f6',
  }
}

// ═══════════════════════════════════════════════════
// 悬停预览
// ═══════════════════════════════════════════════════
const previewVisible = ref(false)
const previewWindowId = ref('')
const previewWindowTitle = ref('')
const previewWindowIcon = ref('')
const previewAnchorRect = ref<{ x: number; y: number; width: number; height: number } | null>(null)

let hoverEnterTimer: ReturnType<typeof setTimeout> | null = null
let hoverLeaveTimer: ReturnType<typeof setTimeout> | null = null

function onItemMouseEnter(event: MouseEvent, item: TaskbarItem) {
  if (hoverLeaveTimer) { clearTimeout(hoverLeaveTimer); hoverLeaveTimer = null }
  hoverEnterTimer = setTimeout(() => {
    const target = (event.currentTarget as HTMLElement)
    const rect = target.getBoundingClientRect()
    previewAnchorRect.value = { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    previewWindowId.value = item.id
    previewWindowTitle.value = item.title
    previewWindowIcon.value = item.icon
    previewVisible.value = true
  }, 300)
}

function onItemMouseLeave() {
  if (hoverEnterTimer) { clearTimeout(hoverEnterTimer); hoverEnterTimer = null }
  hoverLeaveTimer = setTimeout(() => {
    previewVisible.value = false
  }, 150)
}

function onPreviewKeepAlive() {
  if (hoverLeaveTimer) { clearTimeout(hoverLeaveTimer); hoverLeaveTimer = null }
}

function onPreviewDismiss() {
  hoverLeaveTimer = setTimeout(() => {
    previewVisible.value = false
  }, 150)
}

function onPreviewClose(id: string) {
  previewVisible.value = false
  emit('closeWindow', id)
}

// ═══════════════════════════════════════════════════
// 显示桌面
// ═══════════════════════════════════════════════════
const desktopShown = ref(false)

function onShowDesktop() {
  desktopShown.value = !desktopShown.value
  emit('showDesktop')
}

// ═══════════════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════════════
onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (hoverEnterTimer) clearTimeout(hoverEnterTimer)
  if (hoverLeaveTimer) clearTimeout(hoverLeaveTimer)
})
</script>

<style scoped>
.desktop-taskbar {
  position: absolute;
  bottom: 10px;
  left: 50%;
  right: auto;
  width: min(1180px, calc(100% - 32px));
  height: var(--taskbar-height, 58px);
  transform: translateX(-50%);
  background: var(--taskbar-bg, rgba(248, 250, 252, 0.26));
  backdrop-filter: blur(var(--taskbar-blur, 22px)) saturate(var(--desktop-liquid-saturate, 165%));
  -webkit-backdrop-filter: blur(var(--taskbar-blur, 22px)) saturate(var(--desktop-liquid-saturate, 165%));
  border: 1px solid var(--taskbar-top-border, rgba(255, 255, 255, 0.2));
  border-radius: 24px;
  box-shadow:
    var(--desktop-liquid-specular, inset 1px 1px 0 rgba(255,255,255,.46)),
    inset 0 0 0 1px rgba(255,255,255,.06),
    0 18px 48px rgba(15, 23, 42, 0.34);
  display: flex;
  align-items: center;
  padding: 6px;
  gap: 6px;
  z-index: 10000;
  user-select: none;
}
@supports (backdrop-filter: url(#desktop-liquid-refraction)) {
  .desktop-taskbar {
    backdrop-filter: url(#desktop-liquid-refraction) blur(var(--taskbar-blur, 22px)) saturate(var(--desktop-liquid-saturate, 165%));
    -webkit-backdrop-filter: url(#desktop-liquid-refraction) blur(var(--taskbar-blur, 22px)) saturate(var(--desktop-liquid-saturate, 165%));
  }
}
.taskbar-start {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  width: 46px;
  height: 46px;
  padding: 0;
  border-radius: 14px;
  cursor: pointer;
  color: #eff6ff;
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(255, 255, 255, .12);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.18), 0 6px 18px rgba(15,23,42,.16);
  transition: background .16s var(--desktop-ease-out-strong, ease), border-color .16s var(--desktop-ease-out-strong, ease), box-shadow .16s var(--desktop-ease-out-strong, ease), transform .16s var(--desktop-ease-out-strong, ease);
}
.taskbar-start:hover,
.taskbar-start:focus-visible {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(255, 255, 255, 0.3);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.26), 0 10px 24px rgba(15, 23, 42, 0.24);
  transform: translateY(-3px) scale(1.04);
}
.taskbar-start:focus-visible {
  outline: 2px solid rgba(191, 219, 254, .9);
  outline-offset: 2px;
}
.taskbar-start-label { display: none; }
.taskbar-launcher-indicator {
  position: absolute;
  left: 50%;
  bottom: 3px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #e0f2fe;
  transform: translateX(-50%);
  box-shadow: 0 0 12px rgba(224, 242, 254, .9);
}
.taskbar-window-list {
  flex: 1; display: flex; align-items: center;
  gap: 5px; margin: 0 2px; overflow-x: auto;
  scrollbar-width: none;
}
.taskbar-window-list::-webkit-scrollbar {
  display: none;
}
.taskbar-item {
  position: relative; display: flex; align-items: center;
  gap: 7px;
  min-width: 46px;
  max-width: 190px;
  padding: 0 12px;
  height: 44px;
  border-radius: 14px;
  cursor: pointer; color: #cbd5e1; white-space: nowrap; flex-shrink: 0;
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
  transition: background .16s var(--desktop-ease-out-strong, ease), border-color .16s var(--desktop-ease-out-strong, ease), color .16s var(--desktop-ease-out-strong, ease), opacity .16s var(--desktop-ease-out-strong, ease), transform .16s var(--desktop-ease-out-strong, ease), box-shadow .16s var(--desktop-ease-out-strong, ease);
}
.taskbar-item::after {
  content: ''; position: absolute;
  left: 50%;
  right: auto;
  bottom: 4px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: rgba(226, 232, 240, .42);
  transform: translateX(-50%);
}
.taskbar-item:hover,
.taskbar-item:focus-visible {
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.28);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.2), 0 10px 22px rgba(15,23,42,.22);
  transform: translateY(-3px) scale(1.03);
}
.taskbar-item:focus-visible {
  outline: 2px solid rgba(191, 219, 254, .9);
  outline-offset: 2px;
}
.taskbar-item-active {
  background: var(--taskbar-active-bg, rgba(255,255,255,.22));
  border-color: var(--taskbar-active-border, rgba(255,255,255,.34));
  color: #f8fafc;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.26), 0 10px 24px rgba(15,23,42,.22);
}
.taskbar-item-active::after {
  background: #e0f2fe;
  box-shadow: 0 0 12px rgba(224, 242, 254, .9);
}
.taskbar-item-minimized { opacity: 0.66; }
.taskbar-item-minimized::after { background: rgba(203, 213, 225, 0.42); }
.taskbar-window-title {
  font-size: 11px; max-width: 132px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.taskbar-empty { font-size: 12px; color: rgba(226, 232, 240, .72); padding: 0 8px; }
.taskbar-right {
  display: flex; align-items: center; gap: 6px;
  padding-left: 8px;
  border-left: 1px solid rgba(255, 255, 255, 0.14);
}

/* ═══ 进度条 ═══ */
.taskbar-progress-bar {
  position: absolute;
  left: 2px; right: 2px; bottom: 1px;
  height: 2px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.taskbar-progress-fill {
  height: 100%; border-radius: 999px;
  transition: width 0.3s ease;
}
.taskbar-progress-indeterminate {
  width: 40% !important;
  animation: progress-slide 1.4s ease-in-out infinite;
}
@keyframes progress-slide {
  0% { transform: translateX(-100%); }
  50% { transform: translateX(150%); }
  100% { transform: translateX(-100%); }
}

/* ═══ 时钟升级版 ═══ */
.taskbar-clock {
  position: relative;
  display: flex; flex-direction: column; align-items: center;
  justify-content: center;
  min-width: 58px;
  height: 42px;
  padding: 2px 9px; border-radius: 13px;
  cursor: default;
  transition: background 0.15s var(--desktop-ease-out-strong, ease), transform 0.15s var(--desktop-ease-out-strong, ease);
}
.taskbar-clock:hover {
  background: rgba(255, 255, 255, 0.14);
  transform: translateY(-2px);
}
.clock-main {
  font-size: 12px; color: #e2e8f0; font-weight: 600;
  line-height: 1.2;
}
.clock-date {
  font-size: 10px; color: #94a3b8; line-height: 1.2;
}
.clock-panel {
  position: absolute;
  bottom: calc(100% + 8px); left: 50%;
  transform: translateX(-50%);
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(22px) saturate(1.35);
  -webkit-backdrop-filter: blur(22px) saturate(1.35);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 14px;
  padding: 12px 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  white-space: nowrap;
  z-index: 10100;
  text-align: center;
}
.clock-panel-time {
  font-size: 22px; font-weight: 700; color: #f1f5f9;
  letter-spacing: 1px;
}
.clock-panel-date {
  font-size: 12px; color: #cbd5e1; margin-top: 4px;
}
.clock-panel-weekday {
  font-size: 11px; color: #94a3b8; margin-top: 2px;
}
.clock-panel-fade-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.clock-panel-fade-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.clock-panel-fade-enter-from,
.clock-panel-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

/* ═══ 显示桌面按钮 ═══ */
.taskbar-show-desktop {
  width: 14px; height: 42px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  margin-left: 4px;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  transition: background 0.15s ease;
  border-radius: 8px;
}
.taskbar-show-desktop:hover {
  background: rgba(255, 255, 255, 0.1);
}
.taskbar-show-desktop:hover .show-desktop-line {
  opacity: 1;
}
.show-desktop-line {
  width: 2px; height: 16px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 999px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
@media (max-width: 760px) {
  .desktop-taskbar {
    bottom: 8px;
    width: min(100% - 18px, 680px);
    height: 52px;
    border-radius: 20px;
    padding: 5px;
  }
  .taskbar-start,
  .taskbar-item {
    width: 40px;
    min-width: 40px;
    height: 40px;
    padding: 0;
    justify-content: center;
  }
  .taskbar-window-title {
    display: none;
  }
  .taskbar-clock {
    min-width: 48px;
    height: 38px;
  }
  .clock-date {
    display: none;
  }
}
</style>
