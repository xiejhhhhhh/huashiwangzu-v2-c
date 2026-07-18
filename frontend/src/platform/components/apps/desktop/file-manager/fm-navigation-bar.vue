<template>
  <header class="fm-navigation-bar">
    <div class="fm-nav-left">
      <button class="fm-icon-button" type="button" :disabled="!canGoBack" title="后退 ⌘[" aria-label="后退" @click="$emit('go-back')">
        <ChevronLeft :size="17" :stroke-width="2" />
      </button>
      <button class="fm-icon-button" type="button" :disabled="!canGoForward" title="前进 ⌘]" aria-label="前进" @click="$emit('go-forward')">
        <ChevronRight :size="17" :stroke-width="2" />
      </button>
    </div>

    <div class="fm-view-switch" role="group" aria-label="视图">
      <span class="fm-view-thumb" :style="thumbStyle" aria-hidden="true" />
      <button
        v-for="mode in viewModes"
        :key="mode.id"
        type="button"
        class="fm-view-btn"
        :class="{ active: viewMode === mode.id }"
        :title="mode.title"
        :aria-label="mode.title"
        @click="$emit('update:viewMode', mode.id)"
      >
        <component :is="mode.icon" :size="15" :stroke-width="2" />
      </button>
    </div>

    <div class="fm-toolbar-spacer" />

    <div class="fm-tool-group">
      <button
        class="fm-icon-button"
        type="button"
        :class="{ active: showPathBar }"
        title="显示路径栏"
        aria-label="显示路径栏"
        @click="$emit('update:showPathBar', !showPathBar)"
      >
        <FolderTree :size="15" :stroke-width="2" />
      </button>
      <button
        class="fm-icon-button"
        type="button"
        :class="{ active: showPreview }"
        title="显示预览"
        aria-label="显示预览"
        @click="$emit('update:showPreview', !showPreview)"
      >
        <Sidebar :size="15" :stroke-width="2" />
      </button>
      <div class="fm-action-wrap">
        <button
          class="fm-icon-button"
          type="button"
          title="操作"
          aria-label="操作"
          aria-haspopup="menu"
          :aria-expanded="actionOpen"
          @click="actionOpen = !actionOpen"
        >
          <Settings2 :size="15" :stroke-width="2" />
        </button>
        <div v-if="actionOpen" class="fm-action-menu" role="menu">
          <button type="button" role="menuitem" @click="emitAction('upload-file')">上传文件</button>
          <button type="button" role="menuitem" @click="emitAction('create-folder')">新建文件夹</button>
          <button type="button" role="menuitem" @click="emitAction('refresh')">刷新</button>
          <div class="fm-action-sep" />
          <button type="button" role="menuitem" @click="togglePath()">
            {{ showPathBar ? '隐藏路径栏' : '显示路径栏' }}
          </button>
          <button type="button" role="menuitem" @click="togglePreview()">
            {{ showPreview ? '隐藏预览' : '显示预览' }}
          </button>
        </div>
      </div>
    </div>

    <div class="fm-search-pill">
      <Search class="fm-search-icon" :size="13" :stroke-width="2" />
      <input
        class="fm-search-input"
        type="text"
        placeholder="搜索"
        spellcheck="false"
        :value="searchKeyword"
        @input="$emit('update:searchKeyword', ($event.target as HTMLInputElement).value)"
      />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ChevronLeft,
  ChevronRight,
  Columns3,
  FolderTree,
  GalleryHorizontal,
  LayoutGrid,
  List,
  Search,
  Settings2,
  Sidebar,
} from 'lucide-vue-next'
import type { DesktopFileManagerBreadcrumbItem } from './types'

export type FinderViewMode = 'grid' | 'list' | 'column' | 'gallery'

const props = withDefaults(defineProps<{
  canGoBack: boolean
  canGoForward: boolean
  canGoUp: boolean
  breadcrumb: DesktopFileManagerBreadcrumbItem[]
  searchKeyword: string
  viewMode: FinderViewMode
  showPathBar?: boolean
  showPreview?: boolean
}>(), {
  showPathBar: true,
  showPreview: true,
})

const emit = defineEmits<{
  (e: 'go-back'): void
  (e: 'go-forward'): void
  (e: 'go-up'): void
  (e: 'go-root'): void
  (e: 'navigate', index: number): void
  (e: 'update:searchKeyword', value: string): void
  (e: 'update:viewMode', mode: FinderViewMode): void
  (e: 'update:showPathBar', value: boolean): void
  (e: 'update:showPreview', value: boolean): void
  (e: 'action', key: string): void
}>()

const actionOpen = ref(false)

const viewModes = [
  { id: 'grid' as const, title: '图标', icon: LayoutGrid },
  { id: 'list' as const, title: '列表', icon: List },
  { id: 'column' as const, title: '分栏', icon: Columns3 },
  { id: 'gallery' as const, title: '画廊', icon: GalleryHorizontal },
]

const thumbStyle = computed(() => {
  const idx = Math.max(0, viewModes.findIndex((m) => m.id === props.viewMode))
  return { left: `${2 + idx * 30}px` }
})

function emitAction(key: string) {
  actionOpen.value = false
  emit('action', key)
}

function togglePath() {
  actionOpen.value = false
  emit('update:showPathBar', !props.showPathBar)
}

function togglePreview() {
  actionOpen.value = false
  emit('update:showPreview', !props.showPreview)
}

function onDocClick(e: MouseEvent) {
  const t = e.target as HTMLElement | null
  if (!t?.closest('.fm-action-wrap')) actionOpen.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.fm-navigation-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  min-width: 0;
  height: 44px;
  min-height: 44px;
  padding: 0 12px;
  box-sizing: border-box;
  background: transparent;
  box-shadow: inset 0 -0.5px 0 rgba(60, 60, 67, 0.16);
}

.fm-nav-left,
.fm-tool-group {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 1px;
}

.fm-icon-button {
  width: 30px;
  height: 26px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: rgba(60, 60, 67, 0.72);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.fm-icon-button:hover:not(:disabled),
.fm-icon-button.active {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
}

.fm-icon-button.active {
  color: var(--mac-app-accent, #0a84ff);
  background: rgba(10, 132, 255, 0.12);
}

.fm-icon-button:disabled {
  opacity: 0.4;
  cursor: default;
}

.fm-view-switch {
  position: relative;
  display: flex;
  align-items: center;
  margin: 0 8px;
  padding: 2px;
  border-radius: 9px;
  background: rgba(120, 120, 128, 0.14);
  box-shadow: inset 0 0 0 0.5px rgba(60, 60, 67, 0.14);
  flex-shrink: 0;
}

.fm-view-thumb {
  position: absolute;
  top: 2px;
  bottom: 2px;
  width: 30px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.16), inset 0 0 0 0.5px rgba(60, 60, 67, 0.12);
  transition: left 180ms cubic-bezier(0.2, 0.8, 0.2, 1);
  pointer-events: none;
}

.fm-view-btn {
  position: relative;
  z-index: 1;
  width: 30px;
  height: 24px;
  border: 0;
  background: transparent;
  color: rgba(60, 60, 67, 0.68);
  display: grid;
  place-items: center;
  cursor: pointer;
  border-radius: 7px;
}

.fm-view-btn.active {
  color: #1d1d1f;
}

.fm-toolbar-spacer {
  flex: 1;
  min-width: 8px;
}

.fm-action-wrap {
  position: relative;
}

.fm-action-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 40;
  min-width: 168px;
  padding: 6px;
  border-radius: 10px;
  background: rgba(246, 246, 248, 0.94);
  border: 0.5px solid rgba(60, 60, 67, 0.16);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(20px) saturate(160%);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
}

.fm-action-menu button {
  width: 100%;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  padding: 0 10px;
  font: 400 12.5px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: #1d1d1f;
  cursor: pointer;
}

.fm-action-menu button:hover {
  background: rgba(10, 132, 255, 0.16);
}

.fm-action-sep {
  height: 1px;
  margin: 4px 6px;
  background: rgba(60, 60, 67, 0.12);
}

.fm-search-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 188px;
  height: 26px;
  margin-left: 6px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: inset 0 0 0 0.5px rgba(60, 60, 67, 0.16);
  backdrop-filter: blur(16px) saturate(150%);
  -webkit-backdrop-filter: blur(16px) saturate(150%);
  flex-shrink: 0;
}

.fm-search-icon {
  color: rgba(60, 60, 67, 0.55);
  flex-shrink: 0;
}

.fm-search-input {
  width: 100%;
  border: 0;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: #1d1d1f;
}

.fm-search-input::placeholder {
  color: rgba(60, 60, 67, 0.48);
}
</style>
