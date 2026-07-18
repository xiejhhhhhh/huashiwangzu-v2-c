<template>
  <Teleport to="body">
    <Transition name="app-switcher-fade">
      <div v-if="show" class="app-switcher-overlay" @mousedown.self="emit('close')">
        <section class="app-switcher-panel glass-panel" role="dialog" aria-label="App Switcher">
          <div class="app-switcher-row">
            <button
              v-for="(item, index) in items"
              :key="item.id"
              class="app-switcher-item"
              :class="{ 'is-selected': index === selectedIndex }"
              type="button"
              @mouseenter="selectedIndex = index"
              @click="activate(item)"
            >
              <AppIcon :icon="item.icon" :app-key="item.appKey" :size="56" />
              <span>{{ item.title }}</span>
            </button>
          </div>
          <div v-if="!items.length" class="app-switcher-empty">没有打开的窗口</div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from '@/desktop/components/app-icon.vue'
import type { WindowState } from '@/desktop/window-manager/window-types'

const props = defineProps<{ show: boolean; windows: WindowState[] }>()
const emit = defineEmits<{ close: []; activate: [id: string] }>()
const selectedIndex = ref(0)

const items = computed(() => props.windows
  .filter(windowItem => !windowItem.minimized)
  .slice()
  .sort((a, b) => b.zIndex - a.zIndex)
  .map(windowItem => ({
    id: windowItem.id,
    title: windowItem.title,
    icon: windowItem.icon,
    appKey: windowItem.appKey,
  })))

watch(() => props.show, show => {
  if (!show) return
  selectedIndex.value = Math.min(1, Math.max(0, items.value.length - 1))
})
watch(items, list => {
  if (selectedIndex.value >= list.length) selectedIndex.value = Math.max(0, list.length - 1)
})

function move(delta: number) {
  if (!items.value.length) return
  selectedIndex.value = (selectedIndex.value + delta + items.value.length) % items.value.length
}
function activateSelected() {
  const item = items.value[selectedIndex.value]
  if (item) activate(item)
}
function activate(item: { id: string }) {
  emit('activate', item.id)
  emit('close')
}

defineExpose({ move, activateSelected })
</script>

<style scoped>
.app-switcher-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-spotlight);
  display: grid;
  place-items: center;
  background: rgba(4, 9, 18, .12);
}
.app-switcher-panel {
  min-width: min(420px, calc(100vw - 32px));
  max-width: min(860px, calc(100vw - 32px));
  padding: 18px 18px 14px;
  color: var(--desktop-ink);
}
.app-switcher-row {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.app-switcher-item {
  width: 104px;
  min-height: 104px;
  border: 0;
  border-radius: 14px;
  background: transparent;
  color: inherit;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font: var(--desktop-font-caption);
  cursor: default;
}
.app-switcher-item span {
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-switcher-item.is-selected {
  background: color-mix(in srgb, var(--desktop-system-blue) 18%, white);
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--desktop-system-blue) 55%, white);
}
.app-switcher-empty {
  padding: 28px;
  text-align: center;
  color: var(--desktop-ink-muted);
  font: var(--desktop-font-body);
}
.app-switcher-fade-enter-active,
.app-switcher-fade-leave-active {
  transition: opacity var(--desktop-duration-fast) var(--desktop-ease-standard);
}
.app-switcher-fade-enter-from,
.app-switcher-fade-leave-to { opacity: 0; }
</style>
