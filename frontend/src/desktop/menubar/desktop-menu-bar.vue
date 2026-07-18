<template>
  <header ref="menuBarRef" class="mac-menu-bar glass-menubar" :class="{ 'is-solid': solid }" aria-label="系统菜单栏" @mousedown.stop>
    <nav class="mac-menu-bar-primary" aria-label="应用菜单">
      <button class="mac-menu-trigger mac-menu-brand" data-menu-key="brand" type="button" aria-label="华世王镞菜单" :aria-expanded="openMenu === 'brand'" @click="toggleMenu('brand', $event)" @mouseenter="switchOpenMenu('brand', $event)" @keydown="handleTriggerKeydown('brand', $event)">
        <Command :size="15" :stroke-width="2.4" />
      </button>
      <button class="mac-menu-trigger mac-menu-app-title" data-menu-key="app" type="button" :aria-expanded="openMenu === 'app'" @click="toggleMenu('app', $event)" @mouseenter="switchOpenMenu('app', $event)" @keydown="handleTriggerKeydown('app', $event)">{{ activeTitle }}</button>
      <button v-for="menu in menus" :key="menu.key" class="mac-menu-trigger" :data-menu-key="menu.key" type="button" :aria-expanded="openMenu === menu.key" @click="toggleMenu(menu.key, $event)" @mouseenter="switchOpenMenu(menu.key, $event)" @keydown="handleTriggerKeydown(menu.key, $event)">{{ menu.label }}</button>
    </nav>

    <div class="mac-menu-bar-status" aria-label="系统状态">
      <button class="mac-status-button" type="button" title="Spotlight" aria-label="打开 Spotlight" @click="emit('openSpotlight')"><Search :size="14" /></button>
      <DesktopControlCenter @open-spotlight="emit('openSpotlight')" @open-launchpad="emit('openLaunchpad')" />
      <TaskbarNotifications @open-app="(id, payload) => emit('openApp', id, payload)" />
      <button class="mac-status-button mac-account-trigger" data-menu-key="account" type="button" :title="username" aria-label="账户菜单" :aria-expanded="openMenu === 'account'" @click="toggleMenu('account', $event)" @mouseenter="switchOpenMenu('account', $event)" @keydown="handleTriggerKeydown('account', $event)"><UserRound :size="14" /><span>{{ username }}</span></button>
      <time class="mac-clock">{{ clock }}</time>
    </div>

    <div v-if="openMenu" ref="popoverRef" class="mac-menu-popover glass-menu" :class="`mac-menu-popover-${openMenu}`" role="menu" @keydown="handlePopoverKeydown">
      <template v-if="openMenu === 'brand' || openMenu === 'account'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('open-profile')"><UserRound :size="14" /><span>个人资料</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('refresh-desktop')"><RefreshCw :size="14" /><span>刷新桌面</span></button>
        <div class="mac-menu-separator" />
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('logout')"><LogOut :size="14" /><span>退出登录</span></button>
      </template>
      <template v-else-if="openMenu === 'app'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'desktop'); closeMenu()"><FolderOpen :size="14" /><span>打开文件管理</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openLaunchpad'); closeMenu()"><Grid3X3 :size="14" /><span>打开 Launchpad</span></button>
      </template>
      <template v-else-if="openMenu === 'file'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('new-folder')"><FolderPlus :size="14" /><span>新建文件夹</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'desktop'); closeMenu()"><FolderOpen :size="14" /><span>新建文件管理窗口</span></button>
        <div class="mac-menu-separator" />
        <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="closeActive"><X :size="14" /><span>关闭窗口</span></button>
      </template>
      <template v-else-if="openMenu === 'view'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openSpotlight'); closeMenu()"><Search :size="14" /><span>Spotlight</span><kbd v-if="hotkeysEnabled">⌃⇧Space</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openLaunchpad'); closeMenu()"><Grid3X3 :size="14" /><span>Launchpad</span><kbd v-if="hotkeysEnabled">⌃⇧L</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('showDesktop'); closeMenu()"><PanelsTopLeft :size="14" /><span>显示桌面</span><kbd v-if="hotkeysEnabled">⌃⇧D</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('refresh-desktop')"><RefreshCw :size="14" /><span>刷新桌面</span></button>
      </template>
      <template v-else-if="openMenu === 'window'">
        <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="minimizeActive"><Minus :size="14" /><span>最小化</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="zoomActive"><Maximize2 :size="14" /><span>缩放</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('showDesktop'); closeMenu()"><PanelsTopLeft :size="14" /><span>显示桌面</span><kbd v-if="hotkeysEnabled">⌃⇧D / F11</kbd></button>
        <template v-if="windows.length">
          <div class="mac-menu-separator" />
          <button v-for="windowItem in windows" :key="windowItem.id" class="mac-menu-row" type="button" role="menuitem" @click="emit('activateWindow', windowItem.id); closeMenu()">
            <Check v-if="windowItem.id === activeWindowId" :size="14" /><span v-else class="mac-menu-icon-space" />
            <span>{{ windowItem.title }}</span>
          </button>
        </template>
      </template>
      <template v-else-if="openMenu === 'help'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'agent'); closeMenu()"><CircleHelp :size="14" /><span>打开 AI 助手</span></button>
      </template>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import {
  Check, CircleHelp, Command, FolderOpen, FolderPlus, Grid3X3, LogOut, Maximize2,
  Minus, PanelsTopLeft, RefreshCw, Search, UserRound, X,
} from 'lucide-vue-next'
import TaskbarNotifications from '@/desktop/taskbar/taskbar-notifications.vue'
import DesktopControlCenter from '@/desktop/menubar/desktop-control-center.vue'
import type { WindowState } from '@/desktop/window-manager/window-types'
import { desktopConfig } from '@/desktop/config/desktop-preferences'

const props = defineProps<{
  activeTitle: string
  activeWindowId?: string
  username: string
  clock: string
  windows: WindowState[]
}>()
const solid = computed(() => props.windows.some(windowItem => !windowItem.minimized && windowItem.y <= 28))
const hotkeysEnabled = computed(() => Boolean(desktopConfig.enableDesktopHotkeys))

const emit = defineEmits<{
  openApp: [appKey: string, payload?: Record<string, unknown>]
  openSpotlight: []
  openLaunchpad: []
  activateWindow: [id: string]
  minimizeWindow: [id: string]
  zoomWindow: [id: string]
  closeWindow: [id: string]
  showDesktop: []
  command: [command: string]
}>()

const menus = [
  { key: 'file', label: '文件' },
  { key: 'view', label: '查看' },
  { key: 'window', label: '窗口' },
  { key: 'help', label: '帮助' },
]
const openMenu = ref('')
const menuBarRef = ref<HTMLElement | null>(null)
const popoverRef = ref<HTMLElement | null>(null)
let returnFocus: HTMLButtonElement | null = null

function focusFirstMenuItem() {
  nextTick(() => popoverRef.value?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus())
}
function openFromTrigger(key: string, event: Event, focusItem = true) {
  returnFocus = event.currentTarget as HTMLButtonElement
  openMenu.value = key
  if (focusItem) focusFirstMenuItem()
}
function toggleMenu(key: string, event: Event) {
  if (openMenu.value === key) closeMenu(true)
  else openFromTrigger(key, event)
}
function switchOpenMenu(key: string, event: Event) {
  if (openMenu.value && openMenu.value !== key) openFromTrigger(key, event, false)
}
function closeMenu(restoreFocus = true) {
  const target = returnFocus
  openMenu.value = ''
  returnFocus = null
  if (restoreFocus && target?.isConnected) nextTick(() => target.focus())
}
function runCommand(command: string) { emit('command', command); closeMenu() }
function closeActive() { if (props.activeWindowId) emit('closeWindow', props.activeWindowId); closeMenu() }
function minimizeActive() { if (props.activeWindowId) emit('minimizeWindow', props.activeWindowId); closeMenu() }
function zoomActive() { if (props.activeWindowId) emit('zoomWindow', props.activeWindowId); closeMenu() }
function handleTriggerKeydown(key: string, event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    openFromTrigger(key, event)
    return
  }
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const triggers = [...(menuBarRef.value?.querySelectorAll<HTMLButtonElement>('[data-menu-key]') || [])]
  const current = triggers.indexOf(event.currentTarget as HTMLButtonElement)
  const delta = event.key === 'ArrowRight' ? 1 : -1
  const next = triggers[(current + delta + triggers.length) % triggers.length]
  next?.focus()
  if (openMenu.value && next) openFromTrigger(next.dataset.menuKey || '', { currentTarget: next } as unknown as Event)
}
function handlePopoverKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu(true)
    return
  }
  const items = [...(popoverRef.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') || [])]
  if (!items.length || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) return
  event.preventDefault()
  const current = items.indexOf(document.activeElement as HTMLButtonElement)
  const delta = event.key === 'ArrowDown' ? 1 : -1
  items[(current + delta + items.length) % items.length]?.focus()
}
function onDocumentPointerDown(event: PointerEvent) {
  if (!(event.target as HTMLElement | null)?.closest('.mac-menu-bar')) closeMenu(false)
}

onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown))
onUnmounted(() => document.removeEventListener('pointerdown', onDocumentPointerDown))
</script>

<style scoped>
.mac-menu-bar{position:absolute;inset:0 0 auto 0;height:var(--desktop-menu-bar-height);z-index:var(--z-menu-bar);display:flex;align-items:center;justify-content:space-between;padding:0 8px;color:var(--desktop-wallpaper-ink);font:var(--desktop-font-menu);text-shadow:0 1px 2px rgba(0,0,0,.32);user-select:none;transition:background var(--desktop-duration-standard) var(--desktop-ease-standard),backdrop-filter var(--desktop-duration-standard) var(--desktop-ease-standard)}
.mac-menu-bar.is-solid{background:rgba(246,246,250,.72);-webkit-backdrop-filter:var(--desktop-lg-filter-soft,blur(24px) saturate(160%));backdrop-filter:var(--desktop-lg-filter-soft,blur(24px) saturate(160%));text-shadow:none;color:rgba(20,20,22,.88)}
.mac-menu-bar-primary,.mac-menu-bar-status{display:flex;align-items:center;height:100%;min-width:0}.mac-menu-bar-status{gap:1px}
.mac-menu-trigger,.mac-status-button,.mac-clock{height:22px;border:0;border-radius:5px;background:transparent;color:inherit;display:inline-flex;align-items:center;justify-content:center;padding:0 9px;font:inherit;white-space:nowrap;cursor:default}.mac-menu-trigger:hover,.mac-menu-trigger[aria-expanded=true],.mac-status-button:hover,.mac-status-button[aria-expanded=true]{background:rgba(255,255,255,.2)}
.mac-menu-brand{width:34px;padding:0}.mac-menu-app-title{font-weight:700;max-width:190px;overflow:hidden;text-overflow:ellipsis}.mac-account-trigger{gap:5px}.mac-clock{font-weight:600}
.mac-menu-popover{position:absolute;top:26px;left:8px;width:250px;padding:5px;color:var(--desktop-ink);text-shadow:none;z-index:var(--z-system-popover)}
.mac-menu-popover-app{left:42px}.mac-menu-popover-file{left:150px}.mac-menu-popover-view{left:198px}.mac-menu-popover-window{left:250px}.mac-menu-popover-help{left:306px}.mac-menu-popover-account{left:auto;right:8px}
.mac-menu-row{width:100%;height:28px;padding:0 8px;border:0;border-radius:6px;background:transparent;color:inherit;display:grid;grid-template-columns:16px minmax(0,1fr) auto;align-items:center;gap:7px;text-align:left;font:var(--desktop-font-menu);cursor:default}.mac-menu-row:hover:not(:disabled),.mac-menu-row:focus-visible{background:var(--desktop-selection);color:white;outline:none}.mac-menu-row:disabled{opacity:.42}.mac-menu-row kbd{font:inherit;color:var(--desktop-ink-muted)}.mac-menu-row:hover kbd{color:rgba(255,255,255,.78)}.mac-menu-separator{height:1px;margin:4px 7px;background:var(--desktop-divider)}.mac-menu-icon-space{width:14px}
@media(max-width:760px){.mac-menu-trigger:not(.mac-menu-brand):not(.mac-menu-app-title){display:none}.mac-account-trigger span{display:none}.mac-menu-app-title{max-width:120px}.mac-menu-popover{left:8px!important;right:auto!important}}
</style>
