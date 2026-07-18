<template>
  <div class="app-toolbar" :class="[variantClass, { 'app-toolbar-glass': glass }]">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'table' | 'chat' | 'editor'
  glass?: boolean
}>(), {
  variant: 'table',
  glass: true,
})

const variantClass = computed(() => `app-toolbar--${props.variant}`)
</script>

<style scoped>
.app-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: var(--mac-app-toolbar-height, 42px);
  min-height: var(--mac-app-toolbar-height, 42px);
  padding: 0 14px;
  box-sizing: border-box;
  background: transparent;
  flex-shrink: 0;
}
.app-toolbar-glass {
  background: var(--mac-app-surface-toolbar, rgba(255, 255, 255, 0.58));
  border-bottom: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
  backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
  -webkit-backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
}
.app-toolbar--table {
  border-bottom: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
}
.app-toolbar--chat {
  border-bottom: none;
}
.app-toolbar--editor {
  border-bottom: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
}
</style>
