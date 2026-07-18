<template>
  <aside class="fm-nav-pane">
    <div class="fm-nav-section-label">个人收藏</div>
    <button
      class="fm-nav-item"
      :class="{ 'fm-nav-item-active': currentFolderId === 0 && !isRecycleBin }"
      type="button"
      @click="$emit('go-root')"
    >
      <Monitor class="fm-nav-icon" :size="16" :stroke-width="2" />
      <span class="fm-nav-label">桌面</span>
    </button>
    <button
      class="fm-nav-item"
      :class="{ 'fm-nav-item-active': isRecycleBin }"
      type="button"
      @click="$emit('open-recycle')"
    >
      <Trash2 class="fm-nav-icon" :size="16" :stroke-width="2" />
      <span class="fm-nav-label">回收站</span>
    </button>
  </aside>
</template>

<script setup lang="ts">
import { Monitor, Trash2 } from 'lucide-vue-next'

defineProps<{
  currentFolderId: number
  isRecycleBin: boolean
}>()

defineEmits<{
  (e: 'go-root'): void
  (e: 'open-recycle'): void
}>()
</script>

<style scoped>
.fm-nav-pane {
  height: 100%;
  padding: 12px 8px;
  background: transparent;
}

.fm-nav-section-label {
  margin: 0 8px 6px;
  color: var(--mac-app-text-secondary, #77777c);
  font: var(--mac-app-font-caption, 600 11px/1.3 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif);
  font-weight: 600;
}

.fm-nav-item {
  width: 100%;
  height: 30px;
  margin-bottom: 2px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  color: var(--mac-app-text, #303034);
  cursor: pointer;
  text-align: left;
  font-size: 12px;
}

.fm-nav-item:hover {
  background: color-mix(in srgb, var(--mac-app-text, #303034) 6%, transparent);
}

.fm-nav-item-active {
  background: var(--mac-app-selection, rgba(10, 132, 255, 0.14));
  color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 80%, #001);
}

.fm-nav-icon {
  flex-shrink: 0;
  color: var(--mac-app-accent, #0a84ff);
}

.fm-nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
