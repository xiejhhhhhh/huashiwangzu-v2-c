<template>
  <span class="app-icon" :style="styleObject" :data-app-icon-key="profile.key" aria-hidden="true">
    <span class="app-icon-gloss" />
    <component :is="profile.glyph" class="app-icon-glyph" :size="glyphSize" :stroke-width="1.75" />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getAppIconProfile } from './app-icon-catalog'

const props = withDefaults(defineProps<{ icon: string; appKey?: string; size?: number }>(), { size: 20, appKey: '' })

const profile = computed(() => getAppIconProfile(props.appKey, props.icon))
const glyphSize = computed(() => Math.max(11, Math.round(props.size * .5)))
const styleObject = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  '--app-icon-from': profile.value.from,
  '--app-icon-to': profile.value.to,
  '--app-icon-accent': profile.value.accent,
}))
</script>

<style scoped>
.app-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 22%;
  color: var(--app-icon-accent);
  background: linear-gradient(145deg, var(--app-icon-from), var(--app-icon-to));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, .5),
    inset 0 -1px 0 rgba(0, 0, 0, .16),
    0 1px 2px rgba(0, 0, 0, .22),
    0 5px 12px rgba(0, 0, 0, .18);
  isolation: isolate;
}
.app-icon::after {
  content: '';
  position: absolute;
  inset: 1px;
  z-index: -1;
  border: 1px solid rgba(255, 255, 255, .22);
  border-radius: calc(22% - 1px);
}
.app-icon-gloss {
  position: absolute;
  inset: 0 0 44%;
  z-index: -1;
  background: linear-gradient(180deg, rgba(255, 255, 255, .28), rgba(255, 255, 255, .03));
  border-bottom: 1px solid rgba(255, 255, 255, .12);
}
.app-icon-glyph {
  width: 50%;
  height: 50%;
  filter: drop-shadow(0 1px 1px rgba(0, 0, 0, .28));
}
</style>
