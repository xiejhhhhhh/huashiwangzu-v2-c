<template>
  <div class="app-window-frame" :class="[layoutClass, { 'app-window-frame-mac': macChrome }]">
    <AppToolbar v-if="$slots.toolbar" class="app-window-frame_toolbar" :glass="macChrome">
      <slot name="toolbar" />
    </AppToolbar>
    <div class="app-window-frame_body">
      <aside v-if="$slots.sidebar" class="app-window-frame_sidebar" :class="{ collapsed: sidebarCollapsed }" :style="sidebarStyle">
        <slot name="sidebar" />
      </aside>
      <main class="app-window-frame_content">
        <component-error-boundary>
          <slot />
        </component-error-boundary>
      </main>
      <aside v-if="$slots.drawer" class="app-window-frame_drawer" :class="{ visible: drawerVisible }">
        <slot name="drawer" />
      </aside>
    </div>
    <AppStatusBar v-if="$slots.statusbar" class="app-window-frame_statusbar">
      <slot name="statusbar" />
    </AppStatusBar>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppToolbar from './app-toolbar.vue'
import AppStatusBar from './app-status-bar.vue'
import ComponentErrorBoundary from './component-error-boundary.vue'

const props = withDefaults(defineProps<{
  sidebarCollapsed?: boolean
  sidebarWidth?: number
  drawerVisible?: boolean
  layout?: 'management' | 'editor' | 'chat' | 'search' | 'file-manager' | 'dashboard'
  macChrome?: boolean
}>(), {
  sidebarCollapsed: false,
  sidebarWidth: 260,
  drawerVisible: false,
  layout: 'management',
  macChrome: true,
})

const layoutClass = computed(() => `app-window-frame--${props.layout}`)
const sidebarStyle = computed(() => ({
  width: props.sidebarCollapsed ? '0px' : `${props.sidebarWidth}px`,
}))
</script>

<style scoped>
.app-window-frame {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  color: var(--mac-app-text, var(--desktop-ink, #1f2937));
  background: var(--mac-app-surface, transparent);
}
.app-window-frame_toolbar {
  flex-shrink: 0;
}
.app-window-frame_body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.app-window-frame_sidebar {
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.22s ease;
  border-right: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
  background: var(--mac-app-surface-sidebar, rgba(248, 250, 252, 0.72));
}
.app-window-frame-mac .app-window-frame_sidebar {
  background: var(--mac-app-surface-sidebar, rgba(245, 246, 248, 0.78));
  backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
  -webkit-backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
}
.app-window-frame_sidebar.collapsed {
  border-right: none;
}
.app-window-frame_content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: var(--mac-app-surface, linear-gradient(180deg, rgba(252,252,253,.98), rgba(255,255,255,1)));
  box-sizing: border-box;
}
.app-window-frame_drawer {
  flex-shrink: 0;
  width: 0;
  overflow: hidden;
  transition: width 0.22s ease;
  border-left: 1px solid rgba(60, 60, 67, 0.12);
}
.app-window-frame_drawer.visible {
  width: 30%;
  min-width: 280px;
}
.app-window-frame_statusbar {
  flex-shrink: 0;
  border-top: 1px solid rgba(60, 60, 67, 0.1);
  background: rgba(248, 250, 252, 0.86);
}
.app-window-frame--chat .app-window-frame_sidebar {
  border-right: none;
}
.app-window-frame--chat .app-window-frame_content {
  padding: 0;
  background: transparent;
}
.app-window-frame--editor .app-window-frame_content {
  padding: 0;
  display: flex;
  flex-direction: column;
}
.app-window-frame--dashboard .app-window-frame_content {
  padding: 16px;
}
.app-window-frame--file-manager .app-window-frame_content {
  padding: 0;
  background: #fff;
}
</style>
