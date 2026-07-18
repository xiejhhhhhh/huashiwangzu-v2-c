<template>
  <div class="mac-empty-state" role="status">
    <div v-if="$slots.icon || icon" class="mac-empty-state-icon" aria-hidden="true">
      <slot name="icon">{{ icon }}</slot>
    </div>
    <strong class="mac-empty-state-title">{{ title }}</strong>
    <p v-if="description" class="mac-empty-state-desc">{{ description }}</p>
    <div v-if="$slots.action" class="mac-empty-state-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
  icon?: string
}>(), {
  description: '',
  icon: '',
})
</script>

<style scoped>
.mac-empty-state {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 28px 20px;
  text-align: center;
  color: var(--mac-app-text-secondary);
}
.mac-empty-state-icon {
  margin-bottom: 4px;
  opacity: 0.72;
  font-size: 28px;
}
.mac-empty-state-title {
  color: var(--mac-app-text);
  font: var(--mac-app-font-title);
}
.mac-empty-state-desc {
  margin: 0;
  max-width: 320px;
  font: var(--mac-app-font-caption);
  line-height: 1.45;
}
.mac-empty-state-action {
  margin-top: 10px;
}
</style>
