<template>
  <header class="fm-navigation-bar">
    <div class="fm-nav-left">
      <button class="fm-icon-button" type="button" :disabled="!canGoBack" title="后退" aria-label="后退" @click="$emit('go-back')">
        ←
      </button>
      <button class="fm-icon-button" type="button" :disabled="!canGoForward" title="前进" aria-label="前进" @click="$emit('go-forward')">
        →
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
        ↑
      </button>
    </div>

    <div class="fm-nav-address">
      <button
        class="fm-root-btn"
        type="button"
        title="桌面"
        @click="$emit('go-root')"
      >
        🏠
      </button>
      <span v-for="(crumb, index) in breadcrumb" :key="`crumb-${index}`" class="fm-crumb-segment">
        <span class="fm-crumb-sep">&gt;</span>
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
  padding: 4px 12px;
  height: 38px;
  border-bottom: 1px solid #d7e0ea;
  background: rgba(250, 252, 255, 0.92);
  backdrop-filter: blur(8px);
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
  border-radius: 5px;
  background: transparent;
  color: #475569;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fm-icon-button:hover:not(:disabled) {
  background: #eaf0f6;
  border-color: #d4dce8;
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
  gap: 2px;
  padding: 0 8px;
  height: 30px;
  border: 1px solid #d4dce8;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}

.fm-root-btn {
  border: none;
  background: transparent;
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  flex-shrink: 0;
  color: #475569;
}
.fm-root-btn:hover {
  color: #2563eb;
}

.fm-crumb-segment {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.fm-crumb-sep {
  color: #94a3b8;
  font-size: 12px;
  margin: 0 2px;
  flex-shrink: 0;
}

.fm-crumb-btn {
  border: none;
  background: transparent;
  font-size: 12px;
  color: #475569;
  cursor: pointer;
  padding: 2px 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
  border-radius: 3px;
}
.fm-crumb-btn:hover {
  color: #2563eb;
  background: #eaf0f6;
}
.fm-crumb-active {
  color: #1e293b;
  font-weight: 600;
}

.fm-nav-search {
  flex-shrink: 0;
}

.fm-search-input {
  width: 140px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid #d4dce8;
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  color: #1e293b;
  outline: none;
}
.fm-search-input::placeholder {
  color: #94a3b8;
}
.fm-search-input:focus {
  border-color: #60a5fa;
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.15);
}
</style>
