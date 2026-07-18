<template>
  <Teleport to="body">
    <div class="desktop-toast-stack" aria-live="polite" aria-relevant="additions">
      <TransitionGroup name="desktop-toast">
        <div
          v-for="toast in activeToasts"
          :key="toast.id"
          class="desktop-toast glass-banner"
          :class="`desktop-toast-${toast.type}`"
          role="status"
        >
          <span class="desktop-toast-icon" aria-hidden="true">{{ toast.icon }}</span>
          <span class="desktop-toast-message">{{ toast.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { activeToasts } from '@/desktop/feedback/desktop-feedback'
</script>

<style scoped>
.desktop-toast-stack {
  position: fixed;
  left: 50%;
  bottom: calc(var(--desktop-work-bottom-inset) + 18px);
  transform: translateX(-50%);
  z-index: var(--z-system-dialog);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  pointer-events: none;
  width: min(360px, calc(100vw - 32px));
}
.desktop-toast {
  display: grid;
  grid-template-columns: 18px 1fr;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 10px 14px;
  color: var(--desktop-ink);
  pointer-events: none;
}
.desktop-toast-icon {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}
.desktop-toast-message {
  font: var(--desktop-font-body);
  line-height: 1.35;
}
.desktop-toast-success .desktop-toast-icon { color: #1f9d55; }
.desktop-toast-info .desktop-toast-icon { color: #0a84ff; }
.desktop-toast-warning .desktop-toast-icon { color: #d97706; }
.desktop-toast-error .desktop-toast-icon { color: #ef4444; }
.desktop-toast-enter-active,
.desktop-toast-leave-active {
  transition: opacity var(--desktop-duration-fast) var(--desktop-ease-standard),
    transform var(--desktop-duration-standard) var(--desktop-ease-spring);
}
.desktop-toast-enter-from,
.desktop-toast-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(.97);
}
</style>
