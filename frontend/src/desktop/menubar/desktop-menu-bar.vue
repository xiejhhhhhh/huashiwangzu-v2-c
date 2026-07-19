<template>
  <header
    ref="menuBarRef"
    class="mac-menu-bar"
    :class="{ 'is-solid': solid, 'has-open-menu': Boolean(openMenu) }"
    aria-label="系统菜单栏"
    @mousedown.stop
  >
    <nav class="mac-menu-bar-primary" aria-label="应用菜单">
      <button
        class="mac-menu-trigger mac-menu-brand"
        data-menu-key="brand"
        type="button"
        aria-label="华世王镞菜单"
        :aria-expanded="openMenu === 'brand'"
        :class="{ 'is-open': openMenu === 'brand' }"
        @click="toggleMenu('brand', $event)"
        @mouseenter="switchOpenMenu('brand', $event)"
        @keydown="handleTriggerKeydown('brand', $event)"
      >
        <span class="mac-menu-brand-mark" aria-hidden="true">⌘</span>
      </button>
      <button
        class="mac-menu-trigger mac-menu-app-title"
        data-menu-key="app"
        type="button"
        :aria-expanded="openMenu === 'app'"
        :class="{ 'is-open': openMenu === 'app' }"
        @click="toggleMenu('app', $event)"
        @mouseenter="switchOpenMenu('app', $event)"
        @keydown="handleTriggerKeydown('app', $event)"
      >{{ activeTitle }}</button>
      <button
        v-for="menu in menus"
        :key="menu.key"
        class="mac-menu-trigger"
        :data-menu-key="menu.key"
        type="button"
        :aria-expanded="openMenu === menu.key"
        :class="{ 'is-open': openMenu === menu.key }"
        @click="toggleMenu(menu.key, $event)"
        @mouseenter="switchOpenMenu(menu.key, $event)"
        @keydown="handleTriggerKeydown(menu.key, $event)"
      >{{ menu.label }}</button>
    </nav>

    <div class="mac-menu-bar-status" aria-label="系统状态">
      <button class="mac-status-button" type="button" title="Spotlight" aria-label="打开 Spotlight" @click="emit('openSpotlight')">
        <Search :size="13" :stroke-width="2" />
      </button>
      <DesktopControlCenter @open-spotlight="emit('openSpotlight')" @open-launchpad="emit('openLaunchpad')" />
      <TaskbarNotifications @open-app="(id, payload) => emit('openApp', id, payload)" />
      <button
        class="mac-status-button mac-account-trigger"
        data-menu-key="account"
        type="button"
        :title="username"
        aria-label="账户菜单"
        :aria-expanded="openMenu === 'account'"
        :class="{ 'is-open': openMenu === 'account' }"
        @click="toggleMenu('account', $event)"
        @mouseenter="switchOpenMenu('account', $event)"
        @keydown="handleTriggerKeydown('account', $event)"
      >
        <span class="mac-account-name">{{ username }}</span>
      </button>
      <time class="mac-clock">{{ clock }}</time>
    </div>

    <div
      v-if="openMenu"
      ref="popoverRef"
      class="mac-menu-popover"
      :class="`mac-menu-popover-${openMenu}`"
      role="menu"
      @keydown="handlePopoverKeydown"
    >
      <template v-if="openMenu === 'brand' || openMenu === 'account'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('open-profile')"><span>个人资料</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('refresh-desktop')"><span>刷新桌面</span></button>
        <div class="mac-menu-separator" />
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('logout')"><span>退出登录</span></button>
      </template>
      <template v-else-if="openMenu === 'app'">
        <template v-if="isFinderFront">
          <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'desktop'); closeMenu()"><span>关于访达</span></button>
          <div class="mac-menu-separator" />
          <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'desktop'); closeMenu()"><span>新建访达窗口</span><kbd v-if="hotkeysEnabled">⌘N</kbd></button>
          <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('new-folder')"><span>新建文件夹</span><kbd v-if="hotkeysEnabled">⇧⌘N</kbd></button>
          <div class="mac-menu-separator" />
          <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="closeActive"><span>关闭窗口</span><kbd v-if="hotkeysEnabled">⌘W</kbd></button>
        </template>
        <template v-else-if="activeAppKey">
          <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', activeAppKey); closeMenu()"><span>关于 {{ activeTitle }}</span></button>
          <div class="mac-menu-separator" />
          <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="minimizeActive"><span>隐藏 {{ activeTitle }}</span><kbd v-if="hotkeysEnabled">⌘H</kbd></button>
          <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="closeActive"><span>退出 {{ activeTitle }}</span><kbd v-if="hotkeysEnabled">⌘Q</kbd></button>
        </template>
        <template v-else>
          <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'desktop'); closeMenu()"><span>打开访达</span></button>
          <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openLaunchpad'); closeMenu()"><span>打开 Launchpad</span></button>
        </template>
      </template>
      <template v-else-if="openMenu === 'file'">
        <template v-if="injectedFileItems.length">
          <template v-for="item in injectedFileItems" :key="item.id">
            <div v-if="item.separator" class="mac-menu-separator" />
            <button
              v-else
              class="mac-menu-row"
              type="button"
              role="menuitem"
              :disabled="item.disabled || (item.command === 'close-active' && !activeWindowId)"
              @click="runInjected(item)"
            >
              <span>{{ item.label }}</span>
              <kbd v-if="item.shortcut && hotkeysEnabled">{{ item.shortcut }}</kbd>
            </button>
          </template>
        </template>
        <template v-else>
          <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('new-folder')"><span>新建文件夹</span><kbd v-if="hotkeysEnabled">⇧⌘N</kbd></button>
          <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'desktop'); closeMenu()"><span>新建访达窗口</span><kbd v-if="hotkeysEnabled">⌘N</kbd></button>
          <div class="mac-menu-separator" />
          <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="closeActive"><span>关闭窗口</span><kbd v-if="hotkeysEnabled">⌘W</kbd></button>
        </template>
      </template>
      <template v-else-if="openMenu === 'go'">
        <template v-for="item in injectedGoItems" :key="item.id">
          <div v-if="item.separator" class="mac-menu-separator" />
          <button v-else class="mac-menu-row" type="button" role="menuitem" @click="runInjected(item)">
            <span>{{ item.label }}</span>
          </button>
        </template>
      </template>
      <template v-else-if="openMenu === 'view'">
        <template v-if="isFinderFront && injectedViewItems.length">
          <button
            v-for="item in injectedViewItems"
            :key="item.id"
            class="mac-menu-row"
            type="button"
            role="menuitem"
            @click="runInjected(item)"
          ><span>{{ item.label }}</span></button>
          <div class="mac-menu-separator" />
        </template>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openSpotlight'); closeMenu()"><span>Spotlight</span><kbd v-if="hotkeysEnabled">⌃⇧Space</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openLaunchpad'); closeMenu()"><span>Launchpad</span><kbd v-if="hotkeysEnabled">⌃⇧L</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('mission-control'); closeMenu()"><span>调度中心</span><kbd v-if="hotkeysEnabled">⌃⇧M</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('showDesktop'); closeMenu()"><span>显示桌面</span><kbd v-if="hotkeysEnabled">⌃⇧D</kbd></button>
        <div class="mac-menu-separator" />
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('refresh-desktop')"><span>刷新桌面</span></button>
      </template>
      <template v-else-if="openMenu === 'window'">
        <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="minimizeActive"><span>最小化</span><kbd v-if="hotkeysEnabled">⌘M</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" :disabled="!activeWindowId" @click="zoomActive"><span>缩放</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="runCommand('presentation-mode'); closeMenu()"><span>沉浸模式</span><kbd v-if="hotkeysEnabled">⌃⇧F</kbd></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('showDesktop'); closeMenu()"><span>显示桌面</span><kbd v-if="hotkeysEnabled">⌃⇧D</kbd></button>
        <template v-if="windows.length">
          <div class="mac-menu-separator" />
          <button
            v-for="windowItem in windows"
            :key="windowItem.id"
            class="mac-menu-row mac-menu-row-check"
            type="button"
            role="menuitem"
            @click="emit('activateWindow', windowItem.id); closeMenu()"
          >
            <span class="mac-menu-check" :class="{ 'is-on': windowItem.id === activeWindowId }" aria-hidden="true">{{ windowItem.id === activeWindowId ? '✓' : '' }}</span>
            <span class="mac-menu-row-label">{{ windowItem.title }}</span>
          </button>
        </template>
      </template>
      <template v-else-if="openMenu === 'help'">
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'agent'); closeMenu()"><span>华世王镞 帮助</span></button>
        <button class="mac-menu-row" type="button" role="menuitem" @click="emit('openApp', 'agent'); closeMenu()"><span>打开 AI 助手</span></button>
      </template>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Search } from 'lucide-vue-next'
import TaskbarNotifications from '@/desktop/taskbar/taskbar-notifications.vue'
import DesktopControlCenter from '@/desktop/menubar/desktop-control-center.vue'
import type { WindowState } from '@/desktop/window-manager/window-types'
import { desktopConfig } from '@/desktop/config/desktop-preferences'
import { 读取应用菜单, type 菜单项 } from '@/desktop/menubar/应用菜单注册表'

const props = defineProps<{
  activeTitle: string
  activeWindowId?: string
  activeAppKey?: string
  username: string
  clock: string
  windows: WindowState[]
}>()
const solid = computed(() => props.windows.some(windowItem => !windowItem.minimized && windowItem.y <= 28))
const hotkeysEnabled = computed(() => Boolean(desktopConfig.enableDesktopHotkeys))
const activeAppKey = computed(() => props.activeAppKey || '')
const isFinderFront = computed(() => activeAppKey.value === 'desktop' || activeAppKey.value === 'files')
const injectedMenus = computed(() => 读取应用菜单(activeAppKey.value, {
  windowId: props.activeWindowId,
  title: props.activeTitle,
}))
const injectedFileItems = computed(() => injectedMenus.value.find(s => s.key === 'file')?.items || [])
const injectedGoItems = computed(() => injectedMenus.value.find(s => s.key === 'go')?.items || [])
const injectedViewItems = computed(() => injectedMenus.value.find(s => s.key === 'view')?.items || [])

function runInjected(item: 菜单项) {
  if (item.disabled) return
  if (item.openApp) {
    emit('openApp', item.openApp, item.payload)
    closeMenu()
    return
  }
  if (item.command === 'close-active') {
    closeActive()
    return
  }
  if (item.command) {
    runCommand(item.command)
    return
  }
  closeMenu()
}

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

const menus = computed(() => {
  const base = [
    { key: 'file', label: '文件' },
    { key: 'view', label: '查看' },
    { key: 'window', label: '窗口' },
    { key: 'help', label: '帮助' },
  ]
  if (isFinderFront.value) {
    return [
      { key: 'file', label: '文件' },
      { key: 'go', label: '前往' },
      { key: 'view', label: '查看' },
      { key: 'window', label: '窗口' },
      { key: 'help', label: '帮助' },
    ]
  }
  return base
})
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
/* ===== 菜单栏本体：系统默认是“贴壁纸的文字条”，不是玻璃卡片 ===== */
.mac-menu-bar {
  position: absolute;
  inset: 0 0 auto 0;
  height: var(--desktop-menu-bar-height);
  z-index: var(--z-menu-bar);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px 0 10px;
  color: rgba(255, 255, 255, 0.94);
  font: 400 13px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Helvetica Neue", sans-serif;
  letter-spacing: -0.01em;
  /* 极轻阴影，仅保证深浅壁纸上都可读；不要做成厚重浮字 */
  text-shadow: 0 0.5px 1px rgba(0, 0, 0, 0.35);
  user-select: none;
  background: transparent;
  border-bottom: 0;
  -webkit-backdrop-filter: none;
  backdrop-filter: none;
  transition: background 160ms ease, color 160ms ease, text-shadow 160ms ease, border-color 160ms ease;
}

/* 窗口顶到菜单栏：轻微实色 + 细底边，字变深 */
.mac-menu-bar.is-solid {
  background: rgba(246, 246, 248, 0.72);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  backdrop-filter: blur(20px) saturate(140%);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
  color: rgba(29, 29, 31, 0.92);
  text-shadow: none;
}

/* 有菜单打开时也略实一点，避免下拉与壁纸糊在一起 */
.mac-menu-bar.has-open-menu:not(.is-solid) {
  background: rgba(0, 0, 0, 0.08);
  -webkit-backdrop-filter: blur(10px) saturate(120%);
  backdrop-filter: blur(10px) saturate(120%);
}

.mac-menu-bar-primary,
.mac-menu-bar-status {
  display: flex;
  align-items: center;
  height: 100%;
  min-width: 0;
}
.mac-menu-bar-primary { gap: 0; }
.mac-menu-bar-status { gap: 0; margin-left: 8px; }

/* 触发器：系统是矮胶囊，打开态是系统蓝 */
.mac-menu-trigger,
.mac-status-button,
.mac-clock {
  height: 22px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 9px;
  font: inherit;
  white-space: nowrap;
  cursor: default;
  transition: background 80ms ease, color 80ms ease;
}
.mac-menu-trigger {
  padding: 0 8px;
}
.mac-menu-trigger:hover,
.mac-status-button:hover {
  background: rgba(255, 255, 255, 0.14);
}
.mac-menu-trigger.is-open,
.mac-menu-trigger[aria-expanded='true'],
.mac-status-button.is-open,
.mac-status-button[aria-expanded='true'] {
  background: var(--desktop-selection, #0a84ff);
  color: #fff;
  text-shadow: none;
}
.mac-menu-bar.is-solid .mac-menu-trigger:hover,
.mac-menu-bar.is-solid .mac-status-button:hover {
  background: rgba(0, 0, 0, 0.06);
}
.mac-menu-bar.is-solid .mac-menu-trigger.is-open,
.mac-menu-bar.is-solid .mac-menu-trigger[aria-expanded='true'],
.mac-menu-bar.is-solid .mac-status-button.is-open,
.mac-menu-bar.is-solid .mac-status-button[aria-expanded='true'] {
  background: var(--desktop-selection, #0a84ff);
  color: #fff;
}

.mac-menu-brand {
  width: 30px;
  padding: 0;
  font-size: 14px;
  font-weight: 500;
}
.mac-menu-brand-mark {
  display: block;
  line-height: 1;
  transform: translateY(0.5px);
}
.mac-menu-app-title {
  font-weight: 700;
  max-width: 168px;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-left: 7px;
  padding-right: 7px;
}
.mac-account-trigger {
  max-width: 110px;
  padding: 0 7px;
}
.mac-account-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 96px;
  font-weight: 400;
}
.mac-clock {
  padding: 0 6px 0 8px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  opacity: 0.96;
}
.mac-status-button {
  width: 28px;
  padding: 0;
  opacity: 0.96;
}

/* ===== 下拉：系统菜单是紧凑白底，不是带图标的卡片 ===== */
.mac-menu-popover {
  position: absolute;
  top: calc(var(--desktop-menu-bar-height) - 1px);
  left: 8px;
  min-width: 212px;
  max-width: min(320px, calc(100vw - 16px));
  padding: 5px;
  color: rgba(29, 29, 31, 0.92);
  text-shadow: none;
  z-index: var(--z-system-popover);
  border-radius: 8px;
  background: rgba(246, 246, 248, 0.92);
  border: 0.5px solid rgba(0, 0, 0, 0.12);
  box-shadow:
    0 10px 28px rgba(0, 0, 0, 0.22),
    0 2px 6px rgba(0, 0, 0, 0.08),
    inset 0 0.5px 0 rgba(255, 255, 255, 0.65);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  backdrop-filter: blur(40px) saturate(150%);
  animation: mac-menu-in 90ms ease-out;
}
@keyframes mac-menu-in {
  from { opacity: 0; transform: translateY(-2px); }
  to { opacity: 1; transform: translateY(0); }
}
.mac-menu-popover-app { left: 38px; }
.mac-menu-popover-file { left: 118px; }
.mac-menu-popover-go { left: 164px; }
.mac-menu-popover-view { left: 210px; }
.mac-menu-popover-window { left: 258px; }
.mac-menu-popover-help { left: 306px; }
.mac-menu-popover-account { left: auto; right: 8px; }

.mac-menu-row {
  width: 100%;
  min-height: 22px;
  height: 22px;
  padding: 0 10px 0 12px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  text-align: left;
  font: 400 13px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  letter-spacing: -0.01em;
  cursor: default;
}
.mac-menu-row > span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mac-menu-row-check {
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 6px;
  padding-left: 8px;
}
.mac-menu-check {
  width: 14px;
  text-align: center;
  font-size: 11px;
  line-height: 1;
  opacity: 0;
}
.mac-menu-check.is-on { opacity: 1; }
.mac-menu-row-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mac-menu-row:hover:not(:disabled),
.mac-menu-row:focus-visible {
  background: var(--desktop-selection, #0a84ff);
  color: #fff;
  outline: none;
}
.mac-menu-row:disabled {
  opacity: 0.34;
  color: rgba(60, 60, 67, 0.55);
}
.mac-menu-row kbd {
  font: 400 12px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
  color: rgba(60, 60, 67, 0.55);
  letter-spacing: 0.02em;
  justify-self: end;
}
.mac-menu-row:hover kbd,
.mac-menu-row:focus-visible kbd {
  color: rgba(255, 255, 255, 0.78);
}
.mac-menu-separator {
  height: 0.5px;
  margin: 4px 10px;
  background: rgba(60, 60, 67, 0.16);
  border: 0;
}

@media (max-width: 760px) {
  .mac-menu-trigger:not(.mac-menu-brand):not(.mac-menu-app-title) { display: none; }
  .mac-account-name { display: none; }
  .mac-menu-app-title { max-width: 120px; }
  .mac-menu-popover { left: 8px !important; right: auto !important; }
}
@media (prefers-reduced-motion: reduce) {
  .mac-menu-popover { animation: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .mac-menu-bar.is-solid,
  .mac-menu-bar.has-open-menu:not(.is-solid) {
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
  .mac-menu-bar.is-solid { background: #f0f0f2; }
  .mac-menu-popover {
    background: #f4f4f6;
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
}
</style>
