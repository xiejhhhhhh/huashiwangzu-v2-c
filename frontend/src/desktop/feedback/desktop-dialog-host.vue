<template>
  <Teleport to="body">
    <div v-if="dialog" class="desktop-dialog-overlay" @mousedown.self="onCancel">
      <section class="desktop-dialog glass-panel" role="dialog" :aria-labelledby="titleId" :aria-describedby="bodyId">
        <header class="desktop-dialog-header">
          <h2 :id="titleId" class="desktop-dialog-title">{{ dialog.title }}</h2>
        </header>
        <div :id="bodyId" class="desktop-dialog-body">{{ dialog.message }}</div>
        <footer class="desktop-dialog-footer">
          <button v-if="dialog.mode === 'confirm'" type="button" class="desktop-dialog-btn ghost" @click="onCancel">{{ dialog.cancelText }}</button>
          <button type="button" class="desktop-dialog-btn primary" :class="{ danger: dialog.tone === 'warning' || dialog.tone === 'error' }" @click="onConfirm">{{ dialog.confirmText }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { activeDialog, resolveDialog } from '@/desktop/feedback/desktop-feedback'

const dialog = activeDialog
const titleId = computed(() => 'desktop-dialog-title')
const bodyId = computed(() => 'desktop-dialog-body')

function onConfirm() { resolveDialog(true) }
function onCancel() { resolveDialog(false) }
</script>

<style scoped>
.desktop-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-system-dialog);
  display: grid;
  place-items: center;
  background: rgba(4, 9, 18, .28);
  backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
  -webkit-backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
  padding: 24px;
}
.desktop-dialog {
  width: min(420px, calc(100vw - 32px));
  padding: 18px 18px 14px;
  color: var(--desktop-ink);
}
.desktop-dialog-title {
  margin: 0;
  font: 650 15px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
}
.desktop-dialog-body {
  margin-top: 10px;
  white-space: pre-wrap;
  font: var(--desktop-font-body);
  color: var(--desktop-ink-muted);
  line-height: 1.5;
}
.desktop-dialog-footer {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.desktop-dialog-btn {
  min-width: 72px;
  height: 30px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  font: var(--desktop-font-menu);
  cursor: default;
}
.desktop-dialog-btn.ghost {
  background: rgba(60, 60, 67, .08);
  color: var(--desktop-ink);
}
.desktop-dialog-btn.primary {
  background: var(--desktop-system-blue);
  color: white;
}
.desktop-dialog-btn.danger {
  background: #ff3b30;
}
.desktop-dialog-btn:hover { filter: brightness(1.04); }
.desktop-dialog-btn:focus-visible {
  outline: 2px solid rgba(10, 132, 255, .45);
  outline-offset: 2px;
}
</style>
