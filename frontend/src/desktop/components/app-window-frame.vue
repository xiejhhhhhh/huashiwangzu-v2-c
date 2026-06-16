<template>
  <div class="app-window-frame" :class="layoutClass">
    <AppToolbar v-if="$slots.toolbar" class="app-window-frame_toolbar">
      <slot name="toolbar" />
    </AppToolbar>
    <div class="app-window-frame_body">
      <aside v-if="$slots.sidebar" class="app-window-frame_sidebar" :class="{ collapsed: sidebarCollapsed }" :style="sidebarStyle">
        <slot name="sidebar" />
      </aside>
      <main class="app-window-frame_content">
        <slot />
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

const props = withDefaults(defineProps<{
  sidebarCollapsed?: boolean
  sidebarWidth?: number
  drawerVisible?: boolean
  layout?: 'management' | 'editor' | 'chat' | 'search' | 'file-manager' | 'dashboard'
}>(), {
  sidebarCollapsed: false,
  sidebarWidth: 260,
  drawerVisible: false,
  layout: 'management',
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
  border-right: 1px solid var(--边框色, #e4e7ed);
}
.app-window-frame_sidebar.collapsed {
  border-right: none;
}
.app-window-frame_content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: linear-gradient(180deg, #fcfcfd, #ffffff);
  box-sizing: border-box;
}
.app-window-frame_drawer {
  flex-shrink: 0;
  width: 0;
  overflow: hidden;
  transition: width 0.22s ease;
  border-left: 1px solid var(--边框色, #e4e7ed);
}
.app-window-frame_drawer.visible {
  width: 30%;
  min-width: 280px;
}
.app-window-frame_statusbar {
  flex-shrink: 0;
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
</style>
