<template>
  <aside class="fm-nav-pane">
    <div class="fm-nav-section">
      <div class="fm-nav-section-label">个人收藏</div>
      <button
        class="fm-nav-item"
        :class="{ 'fm-nav-item-active': currentFolderId === 0 && !isRecycleBin }"
        type="button"
        @click="$emit('go-root')"
      >
        <span class="fm-nav-glyph fm-nav-glyph-desktop" aria-hidden="true">
          <Monitor :size="14" :stroke-width="2.1" />
        </span>
        <span class="fm-nav-label">桌面</span>
      </button>
    </div>

    <div class="fm-nav-section">
      <div class="fm-nav-section-label">位置</div>
      <button
        class="fm-nav-item"
        :class="{ 'fm-nav-item-active': isRecycleBin }"
        type="button"
        @click="$emit('open-recycle')"
      >
        <span class="fm-nav-glyph fm-nav-glyph-trash" aria-hidden="true">
          <Trash2 :size="14" :stroke-width="2.1" />
        </span>
        <span class="fm-nav-label">回收站</span>
      </button>
    </div>
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
  padding: 12px 10px 14px;
  box-sizing: border-box;
  background: transparent;
}

.fm-nav-section + .fm-nav-section {
  margin-top: 18px;
}

.fm-nav-section-label {
  margin: 0 8px 7px;
  color: color-mix(in srgb, var(--mac-app-text-secondary, #6e6e73) 88%, #000);
  font: 600 11px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  letter-spacing: 0.02em;
  text-transform: none;
  opacity: 0.86;
}

.fm-nav-item {
  width: 100%;
  height: 30px;
  margin-bottom: 2px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 8px;
  color: var(--mac-app-text, rgba(29, 29, 31, 0.92));
  cursor: pointer;
  text-align: left;
  font: 400 13px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  transition: background 0.12s ease, color 0.12s ease;
}

.fm-nav-item:hover {
  background: color-mix(in srgb, var(--mac-app-text, #1d1d1f) 7%, transparent);
}

.fm-nav-item-active {
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 18%, transparent);
  color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 55%, #10243d);
  font-weight: 600;
}

.fm-nav-item-active:hover {
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 22%, transparent);
}

.fm-nav-glyph {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: #fff;
}

.fm-nav-glyph-desktop {
  background: linear-gradient(180deg, #5ac8fa 0%, #0a84ff 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

.fm-nav-glyph-trash {
  background: linear-gradient(180deg, #a1a1a6 0%, #636366 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.fm-nav-item-active .fm-nav-glyph-trash {
  background: linear-gradient(180deg, #8e8e93 0%, #48484a 100%);
}

.fm-nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
