<template>
  <div class="app-toolbar" :class="variantClass">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'table' | 'chat' | 'editor'
}>(), {
  variant: 'table',
})

const variantClass = computed(() => `app-toolbar--${props.variant}`)
</script>

<style scoped>
.app-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  min-height: 40px;
  padding: 0 16px;
  box-sizing: border-box;
  background: transparent;
  flex-shrink: 0;
}
.app-toolbar--table {
  border-bottom: 1px solid var(--边框色, #e4e7ed);
}
.app-toolbar--chat {
  border-bottom: none;
}
.app-toolbar--editor {
  border-bottom: 1px solid var(--边框色, #e4e7ed);
}
</style>
