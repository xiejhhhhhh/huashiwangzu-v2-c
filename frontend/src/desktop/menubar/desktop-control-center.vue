<template>
  <div class="control-center-root" ref="rootRef">
    <button
      ref="triggerRef"
      class="mac-status-button control-center-trigger"
      type="button"
      title="控制中心"
      aria-label="打开控制中心"
      :aria-expanded="open ? 'true' : 'false'"
      @click.stop="toggle"
    >
      <SlidersHorizontal :size="14" :stroke-width="2" />
    </button>

    <div v-if="open" class="control-center-panel glass-panel" role="dialog" aria-label="控制中心" @click.stop>
      <div class="cc-grid">
        <button class="cc-tile" type="button" :class="{ active: hotkeys }" @click="toggleHotkeys">
          <Keyboard :size="16" />
          <div>
            <strong>桌面快捷键</strong>
            <small>{{ hotkeys ? '已开启' : '关闭' }}</small>
          </div>
        </button>
        <button class="cc-tile" type="button" :class="{ active: labels }" @click="toggleLabels">
          <Tags :size="16" />
          <div>
            <strong>图标标签</strong>
            <small>{{ labels ? '显示' : '隐藏' }}</small>
          </div>
        </button>
        <button class="cc-tile" type="button" :class="{ active: autoArrange }" @click="toggleArrange">
          <LayoutGrid :size="16" />
          <div>
            <strong>自动排列</strong>
            <small>{{ autoArrange ? '开启' : '自由' }}</small>
          </div>
        </button>
        <button class="cc-tile" type="button" :class="{ active: lowMemoryOn }" @click="cycleLowMemory">
          <Moon :size="16" />
          <div>
            <strong>低内存模式</strong>
            <small>{{ lowMemoryLabel }}</small>
          </div>
        </button>
      </div>

      <label class="cc-slider">
        <span>显示</span>
        <input v-model.number="brightness" type="range" min="40" max="110" @input="applyBrightness" />
        <strong>{{ brightness }}%</strong>
      </label>

      <div class="cc-wallpaper-row">
        <span>壁纸</span>
        <div class="cc-wallpaper-swatches">
          <button type="button" class="cc-swatch is-image" title="默认" @click="setWallpaper('image', '/desktop/wallpaper-macos-default.svg')" />
          <button type="button" class="cc-swatch is-dusk" title="暮色" @click="setWallpaper('gradient', 'linear-gradient(145deg, #0f172a 0%, #7c3aed 48%, #f97316 100%)')" />
          <button type="button" class="cc-swatch is-ocean" title="海洋" @click="setWallpaper('gradient', 'linear-gradient(160deg, #0c4a6e 0%, #0284c7 42%, #67e8f9 100%)')" />
          <button type="button" class="cc-swatch is-dark" title="深空" @click="setWallpaper('color', '#0b1020')" />
        </div>
      </div>

      <div class="cc-footer">
        <button type="button" class="cc-link" @click="emit('openSpotlight'); close()">Spotlight</button>
        <button type="button" class="cc-link" @click="emit('openLaunchpad'); close()">Launchpad</button>
      </div>
      <div class="cc-hotkey-hint">⌃⇧Space 搜索 · ⌃⇧` 切换 · ⌃⇧L Launchpad · ⌃⇧D 桌面</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Keyboard, LayoutGrid, Moon, SlidersHorizontal, Tags } from 'lucide-vue-next'
import { desktopConfig } from '@/desktop/config/desktop-preferences'
import { 应用低内存样式到根, 同步缓存配额, 是否低内存生效 } from '@/desktop/runtime'

const emit = defineEmits<{ openSpotlight: []; openLaunchpad: [] }>()
const open = ref(false)
const brightness = ref(100)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)

const hotkeys = computed(() => Boolean(desktopConfig.enableDesktopHotkeys))
const labels = computed(() => Boolean(desktopConfig.showIconLabels))
const autoArrange = computed(() => desktopConfig.iconLayout === 'auto-arrange')
const lowMemoryOn = computed(() => 是否低内存生效(desktopConfig))
const lowMemoryLabel = computed(() => {
  const mode = desktopConfig.lowMemoryMode || 'auto'
  if (mode === 'on') return '强制开'
  if (mode === 'off') return '强制关'
  return lowMemoryOn.value ? '自动·已开' : '自动·关闭'
})

function toggle() { open.value = !open.value }
function close() {
  if (!open.value) return
  open.value = false
  triggerRef.value?.focus()
}
function toggleHotkeys() {
  desktopConfig.enableDesktopHotkeys = !desktopConfig.enableDesktopHotkeys
}
function toggleLabels() {
  desktopConfig.showIconLabels = !desktopConfig.showIconLabels
}
function toggleArrange() {
  desktopConfig.iconLayout = desktopConfig.iconLayout === 'auto-arrange' ? 'free' : 'auto-arrange'
}
function cycleLowMemory() {
  const mode = desktopConfig.lowMemoryMode || 'auto'
  desktopConfig.lowMemoryMode = mode === 'auto' ? 'on' : mode === 'on' ? 'off' : 'auto'
  同步缓存配额()
  应用低内存样式到根(document.documentElement)
}
function setWallpaper(type: 'image' | 'gradient' | 'color', value: string) {
  desktopConfig.wallpaperType = type
  desktopConfig.wallpaperValue = value
}
function applyBrightness() {
  const shell = document.querySelector('.desktop-shell-container') as HTMLElement | null
  if (!shell) return
  shell.style.filter = `brightness(${Math.max(0.4, Math.min(1.1, brightness.value / 100))})`
}
function onPointerDown(event: PointerEvent) {
  if (!(event.target as HTMLElement | null)?.closest('.control-center-root')) close()
}
onMounted(() => document.addEventListener('pointerdown', onPointerDown))
onUnmounted(() => document.removeEventListener('pointerdown', onPointerDown))
</script>

<style scoped>
.control-center-root { position: relative; display: flex; align-items: center; }
.control-center-trigger {
  width: 28px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: default;
}
.control-center-trigger:hover { background: rgba(255, 255, 255, 0.14); }
.control-center-trigger[aria-expanded='true'] {
  background: var(--desktop-selection, #0a84ff);
  color: #fff;
}
:global(.mac-menu-bar.is-solid) .control-center-trigger:hover {
  background: rgba(0, 0, 0, 0.06);
}
:global(.mac-menu-bar.is-solid) .control-center-trigger[aria-expanded='true'] {
  background: var(--desktop-selection, #0a84ff);
  color: #fff;
}
.control-center-panel {
  position: absolute;
  top: calc(var(--desktop-menu-bar-height, 28px) + 6px);
  right: 0;
  width: min(320px, calc(100vw - 24px));
  padding: 12px;
  color: var(--desktop-ink);
  z-index: var(--z-system-popover);
  border-radius: 14px;
  background: rgba(246, 246, 248, 0.9);
  border: 0.5px solid rgba(0, 0, 0, 0.1);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.24), inset 0 0.5px 0 rgba(255, 255, 255, 0.55);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  backdrop-filter: blur(40px) saturate(150%);
}
.cc-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.cc-tile {
  min-height: 64px;
  padding: 10px;
  border: 0;
  border-radius: 14px;
  background: color-mix(in srgb, white 62%, transparent);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.42), 0 1px 2px rgba(15,23,42,.04);
  color: inherit;
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 8px;
  align-items: center;
  text-align: left;
  cursor: default;
}
.cc-tile strong { display: block; font: 600 12px/1.25 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif; }
.cc-tile small { color: var(--desktop-ink-muted); font: var(--desktop-font-caption); }
.cc-tile.active {
  background: color-mix(in srgb, var(--desktop-system-blue) 18%, white);
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--desktop-system-blue) 55%, white);
}
.cc-slider {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 42px 1fr 42px;
  gap: 8px;
  align-items: center;
  font: var(--desktop-font-caption);
  color: var(--desktop-ink-muted);
}
.cc-slider input { width: 100%; accent-color: var(--desktop-system-blue); }
.cc-slider strong { text-align: right; color: var(--desktop-ink); font: var(--desktop-font-caption); }
.cc-wallpaper-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  font: 600 12px/1 -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}
.cc-wallpaper-swatches { display: flex; gap: 8px; }
.cc-swatch {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.45), 0 1px 2px rgba(0,0,0,.12);
}
.cc-swatch.is-image { background: linear-gradient(135deg, #7dd3fc, #a78bfa 50%, #fde68a); }
.cc-swatch.is-dusk { background: linear-gradient(145deg, #0f172a, #7c3aed 50%, #f97316); }
.cc-swatch.is-ocean { background: linear-gradient(160deg, #0c4a6e, #0284c7 50%, #67e8f9); }
.cc-swatch.is-dark { background: #0b1020; }
.cc-footer {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.cc-link {
  border: 0;
  background: transparent;
  color: var(--desktop-system-blue);
  font: var(--desktop-font-caption);
  padding: 0;
  cursor: default;
}
.cc-hotkey-hint {
  margin-top: 8px;
  color: rgba(60, 60, 67, 0.62);
  font: 400 10px/1.3 -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}
</style>
