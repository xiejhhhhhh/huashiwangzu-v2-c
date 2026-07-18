<template>
  <div class="app-status-bar">
    <slot />
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.app-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--mac-app-statusbar-height, 26px);
  min-height: var(--mac-app-statusbar-height, 26px);
  padding: 0 12px;
  font: var(--mac-app-font-caption, 400 11px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif);
  color: var(--mac-app-text-secondary, var(--text-info, #909399));
  border-top: 1px solid var(--mac-app-border, var(--border-color, #e4e7ed));
  box-sizing: border-box;
  background: var(--mac-app-surface-status, transparent);
  flex-shrink: 0;
}
</style>
