<template>
  <div v-if="show" class="desktop-launcher-overlay" @click.self="emit('close')">
    <div class="desktop-launcher-panel" @click.stop>
      <div class="desktop-launcher-search"><input v-model="searchText" class="desktop-launcher-search-input" type="text" placeholder="搜索文件和文件夹..." /></div>
      <div class="desktop-launcher-header">开始</div>
      <div class="desktop-launcher-subtitle">已固定</div>
      <div class="desktop-launcher-grid">
        <div v-for="app in filteredAppList" :key="app.appKey" class="desktop-launcher-app-item" @click="emit('openApp', app.appKey)">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { useUserStore } from '@/platform/stores/user'
import AppIcon from '@/desktop/components/app-icon.vue'

const props = defineProps<{
  show: boolean
  appList: AppRegistryEntry[]
}>()

const emit = defineEmits<{
  (e: 'openApp', appKey: string): void
  (e: 'execute-command', command: string): void
  (e: 'close'): void
}>()

const searchText = ref('')
const filteredAppList = computed(() => props.appList.filter(app => !searchText.value.trim() || app.appName.includes(searchText.value.trim())))
const userStore = useUserStore()
const username = computed(() => userStore.userInfo?.display_name || userStore.userInfo?.displayName || userStore.userInfo?.username || '用户')
</script>

<style scoped>
.desktop-launcher-overlay {
  position: absolute; inset: 0; z-index: 9000;
  display: flex; align-items: flex-end; justify-content: flex-start;
  padding: 0 0 48px 8px; background: transparent;
}
.desktop-launcher-panel {
  width: 304px; max-height: 540px; overflow: auto; border-radius: 8px;
  background: rgba(32, 32, 36, 0.96); border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.35); padding: 10px; margin-left: 2px;
  backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
}
.desktop-launcher-search { padding: 0 0 8px; }
.desktop-launcher-search-input { width: 100%; padding: 6px 8px; border: none; border-radius: 4px; background: rgba(255,255,255,.06); color: #e2e8f0; font-size: 11px; outline: none; box-sizing: border-box; }
.desktop-launcher-header { color: #f8fafc; font-size: 14px; font-weight: 700; padding: 2px 4px 8px; }
.desktop-launcher-subtitle { color: rgba(255,255,255,.45); font-size: 11px; padding: 6px 4px; }
.desktop-launcher-subtitle-split { margin-top: 8px; border-top: 1px solid rgba(255,255,255,.08); padding-top: 10px; }
.desktop-launcher-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 6px; }
.desktop-launcher-app-item {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  min-height: 62px; cursor: pointer; border-radius: 8px; color: #e2e8f0;
}
.desktop-launcher-app-item:hover, .desktop-launcher-tool-item:hover { background: rgba(255,255,255,.08); }
.desktop-launcher-app-name { font-size: 10px; max-width: 72px; text-align: center; }
.desktop-launcher-tool-item {
  width: 100%; border: none; background: transparent; color: #cbd5e1; cursor: pointer;
  font-size: 12px; text-align: left; padding: 8px 10px; border-radius: 6px;
  display: flex; align-items: center; gap: 8px;
}
.desktop-launcher-footer { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,.08); display: flex; justify-content: space-between; align-items: center; }
.desktop-launcher-user { font-size: 11px; color: #cbd5e1; }
.desktop-launcher-footer-actions { display: flex; gap: 6px; }
.desktop-launcher-footer-button { width: 26px; height: 26px; border: none; border-radius: 4px; background: transparent; color: #94a3b8; cursor: pointer; }
.desktop-launcher-footer-button:hover { background: rgba(255,255,255,.08); color: #e2e8f0; }
</style>
