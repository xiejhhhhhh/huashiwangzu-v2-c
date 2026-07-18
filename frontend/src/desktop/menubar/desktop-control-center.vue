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
        <button class="cc-tile" type="button" :class="{ active: wifi }" @click="wifi = !wifi">
          <Wifi :size="16" />
          <div>
            <strong>无线局域网</strong>
            <small>{{ wifi ? '已连接' : '关闭' }}</small>
          </div>
        </button>
        <button class="cc-tile" type="button" :class="{ active: bluetooth }" @click="bluetooth = !bluetooth">
          <Bluetooth :size="16" />
          <div>
            <strong>蓝牙</strong>
            <small>{{ bluetooth ? '开启' : '关闭' }}</small>
          </div>
        </button>
        <button class="cc-tile" type="button" :class="{ active: airdrop }" @click="airdrop = !airdrop">
          <Radio :size="16" />
          <div>
            <strong>隔空投送</strong>
            <small>{{ airdrop ? '所有人' : '关闭' }}</small>
          </div>
        </button>
        <button class="cc-tile" type="button" :class="{ active: focus }" @click="focus = !focus">
          <Moon :size="16" />
          <div>
            <strong>专注模式</strong>
            <small>{{ focus ? '勿扰' : '关闭' }}</small>
          </div>
        </button>
      </div>

      <label class="cc-slider">
        <span>显示</span>
        <input v-model.number="brightness" type="range" min="20" max="100" />
        <strong>{{ brightness }}%</strong>
      </label>
      <label class="cc-slider">
        <span>声音</span>
        <input v-model.number="volume" type="range" min="0" max="100" />
        <strong>{{ volume }}%</strong>
      </label>

      <div class="cc-footer">
        <button type="button" class="cc-link" @click="emit('openSpotlight'); close()">Spotlight</button>
        <button type="button" class="cc-link" @click="emit('openLaunchpad'); close()">Launchpad</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Bluetooth, Moon, Radio, SlidersHorizontal, Wifi } from 'lucide-vue-next'

const emit = defineEmits<{ openSpotlight: []; openLaunchpad: [] }>()
const open = ref(false)
const wifi = ref(true)
const bluetooth = ref(true)
const airdrop = ref(false)
const focus = ref(false)
const brightness = ref(78)
const volume = ref(42)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)

function toggle() { open.value = !open.value }
function close() {
  if (!open.value) return
  open.value = false
  triggerRef.value?.focus()
}
function onPointerDown(event: PointerEvent) {
  if (!(event.target as HTMLElement | null)?.closest('.control-center-root')) close()
}
onMounted(() => document.addEventListener('pointerdown', onPointerDown))
onUnmounted(() => document.removeEventListener('pointerdown', onPointerDown))
</script>

<style scoped>
.control-center-root { position: relative; display: flex; align-items: center; }
.control-center-panel {
  position: absolute;
  top: calc(var(--desktop-menu-bar-height, 28px) + 8px);
  right: 0;
  width: min(326px, calc(100vw - 24px));
  padding: 12px;
  color: var(--desktop-ink);
  z-index: var(--z-system-popover);
  border-radius: 22px;
  background: linear-gradient(145deg, color-mix(in srgb, var(--glass-panel-bg) 88%, #d2eefc), var(--glass-panel-bg));
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
</style>
