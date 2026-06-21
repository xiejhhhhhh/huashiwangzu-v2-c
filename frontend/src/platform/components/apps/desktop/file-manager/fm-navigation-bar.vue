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
        class="fm-icon-button drop-target"
        :class="{ 'drop-over': upDropOver }"
        type="button"
        :disabled="!canGoUp"
        title="上级"
        aria-label="上级"
        @click="$emit('go-up')"
        @dragover.prevent="onUpDragOver"
        @dragleave="upDropOver = false"
        @drop.prevent="onUpDrop"
      >
        ↑
      </button>
    </div>

    <div class="fm-nav-address">
      <button
        class="fm-root-btn drop-target"
        :class="{ 'drop-over': rootDropOver }"
        type="button"
        title="桌面"
        @click="$emit('go-root')"
        @dragover.prevent="rootDropOver = true"
        @dragleave="rootDropOver = false"
        @drop.prevent="onRootDrop"
      >
        🏠
      </button>
      <span v-for="(crumb, index) in breadcrumb" :key="`crumb-${index}`" class="fm-crumb-segment">
        <span class="fm-crumb-sep">&gt;</span>
        <button
          class="fm-crumb-btn drop-target"
          :class="{ 'fm-crumb-active': index === breadcrumb.length - 1, 'drop-over': crumbDropIndex === index }"
          type="button"
          @click="$emit('navigate', index)"
          @dragover.prevent="crumbDropIndex = index"
          @dragleave="crumbDropIndex = -1"
          @drop.prevent="onCrumbDrop($event, index, crumb.id ?? undefined)"
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
import { ref } from 'vue'
import type { DesktopFileManagerBreadcrumbItem } from './types'

const props = defineProps<{
  canGoBack: boolean
  canGoForward: boolean
  canGoUp: boolean
  breadcrumb: DesktopFileManagerBreadcrumbItem[]
  searchKeyword: string
}>()

const emit = defineEmits<{
  (e: 'go-back'): void
  (e: 'go-forward'): void
  (e: 'go-up'): void
  (e: 'go-root'): void
  (e: 'navigate', index: number): void
  (e: 'update:searchKeyword', value: string): void
  (e: 'drop-on-target', payload: { sourceType: string; sourceId: number; targetFolderId: number | undefined }): void
}>()

// ── Drag-drop state ──
const rootDropOver = ref(false)
const upDropOver = ref(false)
const crumbDropIndex = ref(-1)

function readDragData(e: DragEvent): { sourceType: string; sourceId: number } | null {
  try {
    const raw = e.dataTransfer?.getData('application/x-fm-drag')
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  // fallback: text/plain has id, but we don't know type — assume 'file'
  const textId = e.dataTransfer?.getData('text/plain')
  if (textId) {
    const id = Number(textId)
    if (Number.isFinite(id)) return { sourceType: 'file', sourceId: id }
  }
  return null
}

function onRootDrop(e: DragEvent) {
  rootDropOver.value = false
  const data = readDragData(e)
  if (!data) return
  emit('drop-on-target', { sourceType: data.sourceType, sourceId: data.sourceId, targetFolderId: undefined })
}

function onUpDragOver(e: DragEvent) {
  if (!props.canGoUp) return
  upDropOver.value = true
}

function onUpDrop(e: DragEvent) {
  upDropOver.value = false
  if (!props.canGoUp) return
  const data = readDragData(e)
  if (!data) return
  // parent folder = second-to-last breadcrumb
  const parentCrumb = props.breadcrumb[props.breadcrumb.length - 2]
  const parentId = parentCrumb?.id ?? undefined
  emit('drop-on-target', { sourceType: data.sourceType, sourceId: data.sourceId, targetFolderId: parentId })
}

function onCrumbDrop(e: DragEvent, index: number, targetFolderId: number | undefined) {
  crumbDropIndex.value = -1
  const data = readDragData(e)
  if (!data) return
  emit('drop-on-target', { sourceType: data.sourceType, sourceId: data.sourceId, targetFolderId })
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

.drop-target.drop-over,
.drop-target.drop-over:hover {
  background: #dbeafe !important;
  border-color: #2395bc !important;
  box-shadow: 0 0 0 2px rgba(35, 149, 188, 0.2);
}
</style>
