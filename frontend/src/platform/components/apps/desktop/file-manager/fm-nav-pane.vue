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
  padding: 13px 9px;
  border-right: 1px solid rgba(60, 60, 67, 0.16);
  background: rgba(235, 235, 235, 0.82);
  backdrop-filter: saturate(150%) blur(18px);
}

.fm-nav-section-label {
  margin: 0 9px 6px;
  color: #77777c;
  font-size: 11px;
  font-weight: 600;
}

.fm-nav-item {
  width: 100%;
  height: 30px;
  margin-bottom: 2px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  color: #303034;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
}

.fm-nav-item:hover {
  background: rgba(60, 60, 67, 0.08);
}

.fm-nav-item-active {
  background: rgba(0, 122, 255, 0.14);
  color: #005ec4;
}

.fm-nav-icon {
  flex-shrink: 0;
  color: var(--desktop-accent, #007aff);
}

.fm-nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
