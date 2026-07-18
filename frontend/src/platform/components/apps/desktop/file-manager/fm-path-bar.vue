<template>
  <div class="fm-path-bar" role="navigation" aria-label="路径">
    <button
      v-for="(crumb, index) in crumbs"
      :key="`${crumb.id ?? 'root'}-${index}`"
      type="button"
      class="fm-path-item"
      :class="{ active: index === crumbs.length - 1 }"
      @click="$emit('navigate', index)"
    >
      <Monitor v-if="index === 0" class="fm-path-glyph" :size="12" :stroke-width="2.1" />
      <Folder v-else class="fm-path-glyph" :size="12" :stroke-width="2.1" />
      <span class="fm-path-label">{{ crumb.name }}</span>
      <ChevronRight
        v-if="index < crumbs.length - 1"
        class="fm-path-sep"
        :size="11"
        :stroke-width="2"
        aria-hidden="true"
      />
    </button>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Folder, Monitor } from 'lucide-vue-next'
import type { DesktopFileManagerBreadcrumbItem } from './types'

defineProps<{
  crumbs: DesktopFileManagerBreadcrumbItem[]
}>()

defineEmits<{
  (e: 'navigate', index: number): void
}>()
</script>

<style scoped>
.fm-path-bar {
  display: flex;
  align-items: center;
  gap: 0;
  min-height: 24px;
  padding: 0 10px;
  overflow-x: auto;
  background: color-mix(in srgb, #f4f4f6 90%, white);
  box-shadow: inset 0 0.5px 0 rgba(60, 60, 67, 0.12);
  white-space: nowrap;
}

.fm-path-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: rgba(60, 60, 67, 0.68);
  font: 400 11px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  cursor: pointer;
  padding: 0 4px;
}

.fm-path-item:hover {
  color: var(--mac-app-accent, #0a84ff);
  background: rgba(10, 132, 255, 0.08);
}

.fm-path-item.active {
  color: #1d1d1f;
  font-weight: 600;
}

.fm-path-glyph {
  flex-shrink: 0;
  opacity: 0.78;
}

.fm-path-item.active .fm-path-glyph {
  opacity: 1;
  color: var(--mac-app-accent, #0a84ff);
}

.fm-path-label {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fm-path-sep {
  margin-left: 2px;
  color: rgba(60, 60, 67, 0.32);
  flex-shrink: 0;
}
</style>
