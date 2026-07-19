<template>
  <Teleport to="body">
    <Transition name="apps-panel-fade">
      <div
        v-if="show"
        class="apps-panel-overlay"
        @mousedown.self="emit('close')"
        @keydown="onKeydown"
      >
        <!-- 新版 macOS 应用程序：居中圆角玻璃弹窗，不是全屏 Launchpad -->
        <section
          ref="panelRef"
          class="apps-panel"
          role="dialog"
          aria-label="应用程序"
          tabindex="-1"
        >
          <header class="apps-panel-header">
            <div class="apps-panel-title-row">
              <span class="apps-panel-brand" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M8 4h3.2v6.4H8V4Zm4.8 0H16v6.4h-3.2V4ZM8 13.6h3.2V20H8v-6.4Zm4.8 0H16V20h-3.2v-6.4Z" fill="currentColor" opacity=".9" />
                  <path d="M4.5 3.5h15A1.5 1.5 0 0 1 21 5v14a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19V5A1.5 1.5 0 0 1 4.5 3.5Z" stroke="currentColor" stroke-width="1.4" opacity=".55" />
                </svg>
              </span>
              <h2 class="apps-panel-title">应用程序</h2>
              <button
                class="apps-panel-more"
                type="button"
                aria-label="更多"
                title="更多"
                @click.stop
              >
                <MoreHorizontal :size="18" :stroke-width="2" />
              </button>
            </div>

            <div class="apps-panel-search">
              <Search class="apps-panel-search-icon" :size="14" :stroke-width="2.1" />
              <input
                ref="searchInputRef"
                v-model="searchText"
                class="apps-panel-search-input"
                type="search"
                placeholder="搜索"
                aria-label="搜索应用"
                autocomplete="off"
                spellcheck="false"
                @keydown.escape.prevent="handleEscape"
              >
            </div>

            <div v-if="categoryChips.length > 1" class="apps-panel-chips" role="tablist" aria-label="应用分类">
              <button
                v-for="chip in categoryChips"
                :key="chip.key"
                class="apps-panel-chip"
                type="button"
                role="tab"
                :aria-selected="activeCategory === chip.key"
                :class="{ 'is-active': activeCategory === chip.key }"
                @click="activeCategory = chip.key"
              >
                {{ chip.label }}
              </button>
            </div>
          </header>

          <div class="apps-panel-body">
            <div v-if="visibleApps.length" class="apps-panel-grid">
              <button
                v-for="app in visibleApps"
                :key="app.appKey"
                class="apps-panel-item"
                type="button"
                :aria-label="app.appName"
                @click="openApp(app.appKey)"
              >
                <AppIcon :icon="app.icon" :app-key="app.appKey" :size="52" />
                <span class="apps-panel-item-name">{{ app.appName }}</span>
              </button>
            </div>
            <div v-else class="apps-panel-empty">没有匹配的应用</div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { MoreHorizontal, Search } from 'lucide-vue-next'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import AppIcon from '@/desktop/components/app-icon.vue'

/** 分类展示名：内部 category 可能是英文 key，映射成更像系统的中文 chip */
const CATEGORY_LABELS: Record<string, string> = {
  ai: 'AI',
  content: '内容',
  files: '文件',
  knowledge: '知识',
  media: '媒体',
  messages: '消息',
  office: '效率',
  system: '系统',
  text: '文本',
  tools: '工具',
  utility: '工具',
  developer: '开发',
  dev: '开发',
  entertainment: '娱乐',
  creative: '创意',
  social: '社交',
  finance: '财务',
  other: '其他',
  '其他': '其他',
  '应用': '应用',
}

const props = defineProps<{ show: boolean; appList: AppRegistryEntry[] }>()
const emit = defineEmits<{ openApp: [appKey: string]; close: []; executeCommand: [command: string] }>()

const searchText = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const activeCategory = ref('all')

function normalizeCategory(raw?: string): string {
  const key = (raw || '其他').trim() || '其他'
  return key
}

function categoryLabel(raw: string): string {
  const lower = raw.toLocaleLowerCase()
  return CATEGORY_LABELS[raw] || CATEGORY_LABELS[lower] || raw
}

const launcherApps = computed(() => (
  props.appList
    .filter(app => app.windowType !== 'background-service')
    .slice()
    .sort((a, b) => (a.sortOrder ?? 100) - (b.sortOrder ?? 100) || a.appName.localeCompare(b.appName, 'zh-CN'))
))

const categoryChips = computed(() => {
  const counts = new Map<string, number>()
  for (const app of launcherApps.value) {
    const key = normalizeCategory(app.category)
    counts.set(key, (counts.get(key) || 0) + 1)
  }
  const chips = [...counts.entries()]
    .map(([key, count]) => ({ key, label: categoryLabel(key), count }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
  return [{ key: 'all', label: '全部', count: launcherApps.value.length }, ...chips]
})

const visibleApps = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase()
  return launcherApps.value.filter(app => {
    const cat = normalizeCategory(app.category)
    if (activeCategory.value !== 'all' && cat !== activeCategory.value) return false
    if (!query) return true
    return `${app.appName} ${app.description || ''} ${app.appKey} ${cat}`.toLocaleLowerCase().includes(query)
  })
})

function openApp(appKey: string) {
  emit('openApp', appKey)
  emit('close')
}

function handleEscape() {
  if (searchText.value) {
    searchText.value = ''
    return
  }
  emit('close')
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    handleEscape()
  }
}

watch(() => props.show, (show) => {
  if (!show) {
    searchText.value = ''
    activeCategory.value = 'all'
    return
  }
  searchText.value = ''
  activeCategory.value = 'all'
  nextTick(() => {
    panelRef.value?.focus({ preventScroll: true })
    searchInputRef.value?.focus({ preventScroll: true })
  })
})

watch(categoryChips, (chips) => {
  if (!chips.some(c => c.key === activeCategory.value)) activeCategory.value = 'all'
})
</script>

<style scoped>
.apps-panel-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-launchpad);
  display: grid;
  place-items: center;
  padding: 28px 20px;
  background: rgba(18, 28, 48, 0.18);
  -webkit-backdrop-filter: blur(10px) saturate(120%);
  backdrop-filter: blur(10px) saturate(120%);
}

/* 圆角大玻璃卡片：对标新版「应用程序」浮层 */
.apps-panel {
  width: min(920px, calc(100vw - 40px));
  height: min(640px, calc(100vh - 72px));
  display: flex;
  flex-direction: column;
  border-radius: 22px;
  overflow: hidden;
  color: rgba(20, 28, 42, 0.92);
  background:
    linear-gradient(165deg, rgba(255, 255, 255, 0.62) 0%, rgba(214, 230, 255, 0.48) 42%, rgba(196, 214, 248, 0.42) 100%);
  border: 0.5px solid rgba(255, 255, 255, 0.55);
  box-shadow:
    0 28px 80px rgba(15, 30, 60, 0.28),
    0 8px 24px rgba(15, 30, 60, 0.14),
    inset 0 0.5px 0 rgba(255, 255, 255, 0.75);
  -webkit-backdrop-filter: blur(40px) saturate(160%);
  backdrop-filter: blur(40px) saturate(160%);
  outline: none;
}

.apps-panel-header {
  flex: 0 0 auto;
  padding: 16px 18px 10px;
  border-bottom: 0.5px solid rgba(60, 80, 120, 0.1);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.28), rgba(255, 255, 255, 0.06));
}

.apps-panel-title-row {
  display: grid;
  grid-template-columns: 28px 1fr 32px;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.apps-panel-brand {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  color: rgba(40, 56, 88, 0.78);
}
.apps-panel-title {
  margin: 0;
  font: 600 17px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  letter-spacing: -0.02em;
  color: rgba(22, 30, 48, 0.92);
}
.apps-panel-more {
  width: 32px;
  height: 28px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(40, 56, 88, 0.62);
  display: grid;
  place-items: center;
  cursor: default;
}
.apps-panel-more:hover {
  background: rgba(255, 255, 255, 0.42);
  color: rgba(22, 30, 48, 0.88);
}

.apps-panel-search {
  height: 32px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 11px;
  margin-bottom: 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.48);
  border: 0.5px solid rgba(255, 255, 255, 0.55);
  box-shadow: inset 0 0.5px 0 rgba(255, 255, 255, 0.7);
}
.apps-panel-search-icon {
  flex: 0 0 auto;
  color: rgba(60, 72, 96, 0.55);
}
.apps-panel-search-input {
  min-width: 0;
  flex: 1;
  height: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: rgba(22, 30, 48, 0.92);
  font: 400 13px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
}
.apps-panel-search-input::placeholder {
  color: rgba(60, 72, 96, 0.45);
}
.apps-panel-search-input::-webkit-search-cancel-button {
  -webkit-appearance: none;
  appearance: none;
}

/* 顶部分类 chip：圆角浅胶囊 */
.apps-panel-chips {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.apps-panel-chips::-webkit-scrollbar { display: none; }
.apps-panel-chip {
  flex: 0 0 auto;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.42);
  color: rgba(36, 48, 72, 0.78);
  font: 500 12px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  letter-spacing: -0.01em;
  white-space: nowrap;
  cursor: default;
  transition: background 120ms ease, color 120ms ease, box-shadow 120ms ease;
}
.apps-panel-chip:hover {
  background: rgba(255, 255, 255, 0.62);
}
.apps-panel-chip.is-active {
  background: rgba(255, 255, 255, 0.86);
  color: rgba(20, 28, 42, 0.92);
  box-shadow: 0 1px 3px rgba(30, 50, 90, 0.1);
}
.apps-panel-chip:focus-visible {
  outline: 2px solid rgba(10, 132, 255, 0.55);
  outline-offset: 2px;
}

.apps-panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 18px 20px;
}

.apps-panel-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 18px 10px;
  align-content: start;
}

.apps-panel-item {
  min-width: 0;
  border: 0;
  padding: 8px 4px 4px;
  border-radius: 14px;
  background: transparent;
  color: inherit;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: default;
  transition: background 120ms ease, transform 140ms cubic-bezier(.22, 1, .36, 1);
}
.apps-panel-item:hover {
  background: rgba(255, 255, 255, 0.38);
  transform: translateY(-1px);
}
.apps-panel-item:active {
  transform: scale(0.97);
  background: rgba(255, 255, 255, 0.5);
}
.apps-panel-item:focus-visible {
  outline: 2px solid rgba(10, 132, 255, 0.55);
  outline-offset: 2px;
}
.apps-panel-item-name {
  max-width: 100%;
  padding: 0 2px;
  font: 400 12px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  letter-spacing: -0.01em;
  color: rgba(28, 36, 52, 0.9);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.apps-panel-empty {
  height: 100%;
  min-height: 180px;
  display: grid;
  place-items: center;
  color: rgba(40, 52, 72, 0.55);
  font: 400 14px/1.4 -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}

.apps-panel-fade-enter-active,
.apps-panel-fade-leave-active {
  transition: opacity 180ms ease;
}
.apps-panel-fade-enter-active .apps-panel,
.apps-panel-fade-leave-active .apps-panel {
  transition: transform 220ms cubic-bezier(.22, 1, .36, 1), opacity 180ms ease;
}
.apps-panel-fade-enter-from,
.apps-panel-fade-leave-to {
  opacity: 0;
}
.apps-panel-fade-enter-from .apps-panel,
.apps-panel-fade-leave-to .apps-panel {
  opacity: 0;
  transform: scale(0.96) translateY(8px);
}

@media (max-width: 900px) {
  .apps-panel-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .apps-panel { height: min(620px, calc(100vh - 48px)); }
}
@media (max-width: 640px) {
  .apps-panel-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px 8px; }
  .apps-panel { border-radius: 18px; width: calc(100vw - 20px); }
  .apps-panel-header { padding-inline: 14px; }
  .apps-panel-body { padding-inline: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .apps-panel-fade-enter-active,
  .apps-panel-fade-leave-active,
  .apps-panel-fade-enter-active .apps-panel,
  .apps-panel-fade-leave-active .apps-panel,
  .apps-panel-item {
    transition: none !important;
  }
  .apps-panel-item:hover,
  .apps-panel-item:active { transform: none; }
}
@media (prefers-reduced-transparency: reduce) {
  .apps-panel-overlay {
    background: rgba(18, 28, 48, 0.45);
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
  .apps-panel {
    background: #e8eef8;
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
}
</style>
