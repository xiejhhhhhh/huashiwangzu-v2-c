<template>
  <header class="fm-navigation-bar">
    <div class="fm-nav-left">
      <button class="fm-icon-button" type="button" :disabled="!canGoBack" title="后退" aria-label="后退" @click="$emit('go-back')">
        <ChevronLeft :size="17" :stroke-width="2" />
      </button>
      <button class="fm-icon-button" type="button" :disabled="!canGoForward" title="前进" aria-label="前进" @click="$emit('go-forward')">
        <ChevronRight :size="17" :stroke-width="2" />
      </button>
      <button
        v-if="canGoUp"
        class="fm-icon-button"
        type="button"
        title="上级"
        aria-label="上级"
        :data-folder="parentFolderId() || undefined"
        @click="$emit('go-up')"
      >
        <ArrowUp :size="16" :stroke-width="2" />
      </button>
    </div>

    <div class="fm-nav-address">
      <button class="fm-root-btn" type="button" title="桌面" @click="$emit('go-root')">
        <Monitor :size="15" :stroke-width="2" />
      </button>
      <span v-for="(crumb, index) in breadcrumb" :key="`crumb-${index}`" class="fm-crumb-segment">
        <ChevronRight class="fm-crumb-sep" :size="13" :stroke-width="1.75" />
        <button
          class="fm-crumb-btn"
          :class="{ 'fm-crumb-active': index === breadcrumb.length - 1 }"
          type="button"
          :data-folder="crumb.id ?? undefined"
          @click="$emit('navigate', index)"
        >
          {{ crumb.name }}
        </button>
      </span>
    </div>

    <div class="fm-nav-search">
      <Search class="fm-search-icon" :size="14" :stroke-width="2" />
      <input
        class="fm-search-input"
        type="text"
        placeholder="搜索"
        :value="searchKeyword"
        @input="$emit('update:searchKeyword', ($event.target as HTMLInputElement).value)"
      />
    </div>
  </header>
</template>

<script setup lang="ts">
import { ArrowUp, ChevronLeft, ChevronRight, Monitor, Search } from 'lucide-vue-next'
import type { DesktopFileManagerBreadcrumbItem } from './types'

const props = defineProps<{
  canGoBack: boolean
  canGoForward: boolean
  canGoUp: boolean
  breadcrumb: DesktopFileManagerBreadcrumbItem[]
  searchKeyword: string
}>()

defineEmits<{
  (e: 'go-back'): void
  (e: 'go-forward'): void
  (e: 'go-up'): void
  (e: 'go-root'): void
  (e: 'navigate', index: number): void
  (e: 'update:searchKeyword', value: string): void
}>()

const parentFolderId = () => {
  if (props.breadcrumb.length < 2) return ''
  return props.breadcrumb[props.breadcrumb.length - 2]?.id ?? ''
}
</script>

<style scoped>
.fm-navigation-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  padding: 0 10px;
  min-height: var(--mac-app-toolbar-height, 42px);
  background: transparent;
}

.fm-nav-left {
  display: flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
  padding: 2px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--mac-app-border, rgba(60, 60, 67, 0.12)) 55%, transparent);
}

.fm-icon-button {
  width: 28px;
  height: 26px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--mac-app-text, #343438);
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fm-icon-button:hover:not(:disabled) {
  background: color-mix(in srgb, white 70%, transparent);
}
.fm-icon-button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.fm-nav-address {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 0 8px;
  height: 28px;
  border: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.14));
  border-radius: 8px;
  background: color-mix(in srgb, white 72%, transparent);
  overflow: hidden;
}

.fm-root-btn {
  border: none;
  background: transparent;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  flex-shrink: 0;
  color: var(--mac-app-text-secondary, #4b4b50);
}
.fm-root-btn:hover {
  color: var(--mac-app-accent, #0a84ff);
}

.fm-crumb-segment {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.fm-crumb-sep {
  color: var(--mac-app-text-secondary, #99999f);
  margin: 0 2px;
  flex-shrink: 0;
}

.fm-crumb-btn {
  border: none;
  background: transparent;
  font-size: 12px;
  color: var(--mac-app-text-secondary, #55555a);
  cursor: pointer;
  padding: 2px 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
  border-radius: 5px;
}
.fm-crumb-btn:hover {
  color: var(--mac-app-accent, #0a84ff);
  background: var(--mac-app-selection, rgba(10, 132, 255, 0.12));
}
.fm-crumb-active {
  color: var(--mac-app-text, #1d1d1f);
  font-weight: 600;
}

.fm-nav-search {
  position: relative;
  flex-shrink: 0;
}

.fm-search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  z-index: 1;
  color: var(--mac-app-text-secondary, #8e8e93);
  pointer-events: none;
  transform: translateY(-50%);
}

.fm-search-input {
  width: 148px;
  height: 28px;
  padding: 0 9px 0 27px;
  border: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.14));
  border-radius: 8px;
  background: color-mix(in srgb, white 72%, transparent);
  font-size: 12px;
  color: var(--mac-app-text, #1d1d1f);
  outline: none;
}
.fm-search-input::placeholder {
  color: var(--mac-app-text-secondary, #8e8e93);
}
.fm-search-input:focus {
  border-color: var(--mac-app-accent, #0a84ff);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--mac-app-accent, #0a84ff) 18%, transparent);
}

@media (max-width: 720px) {
  .fm-nav-address { display: none; }
  .fm-nav-search { flex: 1; }
  .fm-search-input { width: 100%; }
}
</style>
