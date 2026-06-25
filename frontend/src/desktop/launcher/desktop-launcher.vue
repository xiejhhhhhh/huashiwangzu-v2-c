<template>
  <div v-if="show" class="desktop-launcher-overlay" @click.self="emit('close')">
    <div class="desktop-launcher-panel" @click.stop>
      <div class="desktop-launcher-search">
        <input
          ref="searchInputRef"
          v-model="searchText"
          class="desktop-launcher-search-input"
          type="text"
          name="launcher-search"
          placeholder="搜索应用、命令、文件..."
          @input="onSearchInput"
        />
      </div>

      <!-- Search results -->
      <template v-if="searchText.trim()">
        <div v-if="rawResults.length === 0" class="desktop-launcher-empty">未找到匹配项</div>
        <div v-else class="desktop-launcher-results">
          <div v-for="group in groupedResults" :key="group.label" class="desktop-launcher-group">
            <div class="desktop-launcher-group-label">{{ group.label }}</div>
            <div
              v-for="item in group.items"
              :key="item.id"
              class="desktop-launcher-result-item"
              :class="{ 'desktop-launcher-result-active': activeIndex === item._index }"
              @click="executeItem(item)"
              @mouseenter="activeIndex = item._index"
            >
              <span class="desktop-launcher-result-icon">{{ item.icon || defaultIcon(item.type) }}</span>
              <div class="desktop-launcher-result-content">
                <span class="desktop-launcher-result-title">{{ item.title }}</span>
                <span v-if="item.description" class="desktop-launcher-result-desc">{{ item.description }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Default pinned apps (no search) -->
      <template v-else>
        <div class="desktop-launcher-header">开始</div>
        <div class="desktop-launcher-subtitle">已固定</div>
        <div class="desktop-launcher-grid">
          <div v-for="app in appList" :key="app.appKey" class="desktop-launcher-app-item" @click="emit('openApp', app.appKey)">
            <AppIcon :icon="app.icon" :size="28" />
            <span class="desktop-launcher-app-name">{{ app.appName }}</span>
          </div>
        </div>
        <div class="desktop-launcher-subtitle desktop-launcher-subtitle-split">系统工具</div>
        <button class="desktop-launcher-tool-item" type="button" @click="emit('execute-command', 'refresh-desktop')"><span>🔄</span><span>刷新桌面</span></button>
        <button class="desktop-launcher-tool-item" type="button" @click="emit('execute-command', 'minimize-all')"><span>🪟</span><span>最小化所有窗口</span></button>
        <button class="desktop-launcher-tool-item" type="button" @click="emit('execute-command', 'restore-all')"><span>📐</span><span>还原全部窗口</span></button>
        <button class="desktop-launcher-tool-item" type="button" @click="emit('openApp', 'desktop')"><span>📂</span><span>文件管理</span></button>
        <button class="desktop-launcher-tool-item" type="button" @click="emit('openApp', 'recycle')"><span>🗑</span><span>回收站</span></button>
        <div class="desktop-launcher-footer">
          <span class="desktop-launcher-user">👤 {{ username }}</span>
          <div class="desktop-launcher-footer-actions">
            <button class="desktop-launcher-footer-button" type="button" @click="emit('execute-command', 'logout')">🚪</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { useUserStore } from '@/platform/stores/user'
import AppIcon from '@/desktop/components/app-icon.vue'
import { commandRegistry } from '@/desktop/app-registry/command-registry'
import type { SearchResultItem } from '@/desktop/app-registry/command-registry'

const props = defineProps<{
  show: boolean
  appList: AppRegistryEntry[]
}>()

const emit = defineEmits<{
  (e: 'openApp', appKey: string): void
  (e: 'execute-command', command: string): void
  (e: 'close'): void
}>()

const searchInputRef = ref<HTMLInputElement | null>(null)
const searchText = ref('')
const activeIndex = ref(-1)

const userStore = useUserStore()
const username = computed(() => userStore.userInfo?.display_name || userStore.userInfo?.displayName || userStore.userInfo?.username || '用户')

const rawResults = ref<(SearchResultItem & { _index: number })[]>([])

function onSearchInput() {
  const q = searchText.value.trim()
  if (!q) {
    rawResults.value = []
    activeIndex.value = -1
    return
  }
  const cmdResults = commandRegistry.search(q)

  const items: (SearchResultItem & { _index: number })[] = cmdResults.map((r, i) => ({ ...r, _index: i }))
  rawResults.value = items
  activeIndex.value = items.length > 0 ? 0 : -1
}

interface ResultGroup {
  label: string
  items: (SearchResultItem & { _index: number })[]
}

const groupedResults = computed<ResultGroup[]>(() => {
  const groups: Record<string, (SearchResultItem & { _index: number })[]> = {}
  for (const item of rawResults.value) {
    const cat = item.category || '其他'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(item)
  }
  return Object.entries(groups).map(([label, items]) => ({ label, items }))
})

function defaultIcon(type: string): string {
  if (type === 'app') return '📱'
  if (type === 'command') return '⚡'
  if (type === 'action') return '🔧'
  if (type === 'file') return '📄'
  return '📌'
}

function executeItem(item: SearchResultItem & { _index: number }) {
  item.execute()
  emit('close')
}

watch(() => props.show, (val) => {
  if (val) {
    searchText.value = ''
    rawResults.value = []
    activeIndex.value = -1
    nextTick(() => searchInputRef.value?.focus())
  }
})
</script>

<style scoped>
.desktop-launcher-overlay {
  position: absolute; inset: 0; z-index: 9000;
  display: flex; align-items: flex-end; justify-content: flex-start;
  padding: 0 0 48px 8px; background: transparent;
}
.desktop-launcher-panel {
  width: 360px; max-height: 540px; overflow: hidden; border-radius: 8px;
  background: rgba(32, 32, 36, 0.96); border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.35); padding: 10px; margin-left: 2px;
  backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
  display: flex; flex-direction: column;
}
.desktop-launcher-search { padding: 0 0 8px; flex-shrink: 0; }
.desktop-launcher-search-input { width: 100%; padding: 6px 8px; border: none; border-radius: 4px; background: rgba(255,255,255,.06); color: #e2e8f0; font-size: 11px; outline: none; box-sizing: border-box; }
.desktop-launcher-results { flex: 1; overflow-y: auto; min-height: 0; }
.desktop-launcher-empty { padding: 20px 8px; text-align: center; color: rgba(255,255,255,.35); font-size: 12px; }
.desktop-launcher-group { margin-bottom: 4px; }
.desktop-launcher-group-label { color: rgba(255,255,255,.35); font-size: 10px; text-transform: uppercase; padding: 4px 8px; letter-spacing: 0.5px; }
.desktop-launcher-result-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px;
  cursor: pointer; color: #e2e8f0; min-height: 36px;
}
.desktop-launcher-result-item:hover,
.desktop-launcher-result-active { background: rgba(255,255,255,.1); }
.desktop-launcher-result-icon { width: 20px; text-align: center; font-size: 14px; flex-shrink: 0; }
.desktop-launcher-result-content { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.desktop-launcher-result-title { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.desktop-launcher-result-desc { font-size: 10px; color: rgba(255,255,255,.4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.desktop-launcher-header { color: #f8fafc; font-size: 14px; font-weight: 700; padding: 2px 4px 8px; flex-shrink: 0; }
.desktop-launcher-subtitle { color: rgba(255,255,255,.45); font-size: 11px; padding: 6px 4px; flex-shrink: 0; }
.desktop-launcher-subtitle-split { margin-top: 8px; border-top: 1px solid rgba(255,255,255,.08); padding-top: 10px; }
.desktop-launcher-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 6px; flex-shrink: 0; }
.desktop-launcher-app-item {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  min-height: 62px; cursor: pointer; border-radius: 8px; color: #e2e8f0;
}
.desktop-launcher-app-item:hover, .desktop-launcher-tool-item:hover { background: rgba(255,255,255,.08); }
.desktop-launcher-app-name { font-size: 10px; max-width: 72px; text-align: center; }
.desktop-launcher-tool-item {
  width: 100%; border: none; background: transparent; color: #cbd5e1; cursor: pointer;
  font-size: 12px; text-align: left; padding: 8px 10px; border-radius: 6px;
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.desktop-launcher-footer { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,.08); display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; }
.desktop-launcher-user { font-size: 11px; color: #cbd5e1; }
.desktop-launcher-footer-actions { display: flex; gap: 6px; }
.desktop-launcher-footer-button { width: 26px; height: 26px; border: none; border-radius: 4px; background: transparent; color: #94a3b8; cursor: pointer; }
.desktop-launcher-footer-button:hover { background: rgba(255,255,255,.08); color: #e2e8f0; }
</style>
