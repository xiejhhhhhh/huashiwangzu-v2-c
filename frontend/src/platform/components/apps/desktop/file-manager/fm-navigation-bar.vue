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
      <button
        class="fm-root-btn"
        type="button"
        title="桌面"
        @click="$emit('go-root')"
      >
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
  padding: 5px 12px;
  min-height: 42px;
  border-bottom: 1px solid rgba(60, 60, 67, 0.18);
  background: rgba(246, 246, 246, 0.88);
  backdrop-filter: saturate(160%) blur(18px);
}

.fm-nav-left {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.fm-icon-button {
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #343438;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fm-icon-button:hover:not(:disabled) {
  background: rgba(60, 60, 67, 0.1);
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
  padding: 0 7px;
  height: 29px;
  border: 1px solid rgba(60, 60, 67, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.72);
  overflow: hidden;
}

.fm-root-btn {
  border: none;
  background: transparent;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  flex-shrink: 0;
  color: #4b4b50;
}
.fm-root-btn:hover {
  color: var(--desktop-accent, #007aff);
}

.fm-crumb-segment {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.fm-crumb-sep {
  color: #99999f;
  margin: 0 2px;
  flex-shrink: 0;
}

.fm-crumb-btn {
  border: none;
  background: transparent;
  font-size: 12px;
  color: #55555a;
  cursor: pointer;
  padding: 2px 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
  border-radius: 3px;
}
.fm-crumb-btn:hover {
  color: var(--desktop-accent, #007aff);
  background: rgba(60, 60, 67, 0.08);
}
.fm-crumb-active {
  color: #1d1d1f;
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
  color: #8e8e93;
  pointer-events: none;
  transform: translateY(-50%);
}

.fm-search-input {
  width: 140px;
  height: 28px;
  padding: 0 9px 0 27px;
  border: 1px solid rgba(60, 60, 67, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  color: #1d1d1f;
  outline: none;
}
.fm-search-input::placeholder {
  color: #8e8e93;
}
.fm-search-input:focus {
  border-color: var(--desktop-accent, #007aff);
  box-shadow: 0 0 0 2px rgba(0, 122, 255, 0.14);
}

@media (max-width: 720px) {
  .fm-nav-address { display: none; }
  .fm-nav-search { flex: 1; }
  .fm-search-input { width: 100%; }
}
</style>
