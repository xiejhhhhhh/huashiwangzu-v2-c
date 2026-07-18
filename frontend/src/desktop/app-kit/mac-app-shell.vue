<template>
  <div
    class="mac-app-kit"
    :class="[`mac-app-layout-${layout}`, `mac-app-density-${density}`]"
    :data-mac-app-kit="kitId"
    :data-mac-app-layout="layout"
  >
    <AppWindowFrame
      :layout="frameLayout"
      :sidebar-collapsed="sidebarCollapsed"
      :sidebar-width="sidebarWidth"
      :drawer-visible="drawerVisible"
      :mac-chrome="true"
    >
      <template v-if="$slots.toolbar" #toolbar>
        <slot name="toolbar" />
      </template>
      <template v-if="$slots.sidebar" #sidebar>
        <slot name="sidebar" />
      </template>
      <template v-if="$slots.drawer" #drawer>
        <slot name="drawer" />
      </template>
      <template v-if="$slots.statusbar" #statusbar>
        <slot name="statusbar" />
      </template>
      <slot />
    </AppWindowFrame>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppWindowFrame from '@/desktop/components/app-window-frame.vue'
import {
  MAC_APP_KIT_ID,
  toWindowFrameLayout,
  type MacAppDensity,
  type MacAppLayout,
} from './types'
import './tokens-app.css'

const props = withDefaults(defineProps<{
  layout?: MacAppLayout
  density?: MacAppDensity
  sidebarCollapsed?: boolean
  sidebarWidth?: number
  drawerVisible?: boolean
}>(), {
  layout: 'utility',
  density: 'comfortable',
  sidebarCollapsed: false,
  sidebarWidth: 220,
  drawerVisible: false,
})

const kitId = MAC_APP_KIT_ID
const frameLayout = computed(() => toWindowFrameLayout(props.layout))
</script>

<style scoped>
.mac-app-kit {
  height: 100%;
  min-height: 0;
}
.mac-app-density-compact {
  --mac-app-toolbar-height: 38px;
  --mac-app-sidebar-width: 200px;
}
</style>
