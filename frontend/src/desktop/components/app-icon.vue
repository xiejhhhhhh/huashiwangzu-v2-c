<template>
  <span
    class="app-icon"
    :class="[`app-icon-material-${profile.material}`, { 'app-icon-sm': size <= 22 }]"
    :style="styleObject"
    :data-app-icon-key="profile.key"
    aria-hidden="true"
  >
    <span class="app-icon-base" />
    <span class="app-icon-sheen" />
    <span class="app-icon-rim" />
    <component :is="profile.glyph" class="app-icon-glyph" :size="glyphSize" :stroke-width="glyphStroke" />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getAppIconProfile } from './app-icon-catalog'

const props = withDefaults(defineProps<{ icon: string; appKey?: string; size?: number }>(), { size: 20, appKey: '' })

const profile = computed(() => getAppIconProfile(props.appKey, props.icon))
const glyphSize = computed(() => Math.max(11, Math.round(props.size * (props.size >= 40 ? 0.48 : 0.5))))
const glyphStroke = computed(() => (props.size >= 40 ? 1.65 : 1.85))
const styleObject = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  '--app-icon-from': profile.value.from,
  '--app-icon-to': profile.value.to,
  '--app-icon-accent': profile.value.accent,
  '--app-icon-depth': profile.value.depth || 'rgba(0,0,0,.22)',
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
  border-radius: 22.37%;
  color: var(--app-icon-accent);
  isolation: isolate;
  transform: translateZ(0);
}
.app-icon-base {
  position: absolute;
  inset: 0;
  z-index: -3;
  border-radius: inherit;
  background:
    radial-gradient(circle at 28% 22%, rgba(255,255,255,.34), transparent 34%),
    linear-gradient(160deg, var(--app-icon-from), var(--app-icon-to));
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.55),
    inset 0 -2px 4px var(--app-icon-depth),
    0 1px 2px rgba(0,0,0,.22),
    0 8px 16px rgba(0,0,0,.18);
}
.app-icon-sheen {
  position: absolute;
  inset: 0 0 46%;
  z-index: -2;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255,255,255,.34), rgba(255,255,255,.04));
  border-bottom: 1px solid rgba(255,255,255,.12);
  pointer-events: none;
}
.app-icon-rim {
  position: absolute;
  inset: 0;
  z-index: -1;
  border-radius: inherit;
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,.28),
    inset 0 0 0 1.5px rgba(0,0,0,.08);
  pointer-events: none;
}
.app-icon-glyph {
  width: 50%;
  height: 50%;
  filter: drop-shadow(0 1px 1px rgba(0,0,0,.28));
  position: relative;
  z-index: 1;
}
.app-icon-material-paper .app-icon-base {
  background:
    radial-gradient(circle at 30% 18%, rgba(255,255,255,.5), transparent 30%),
    linear-gradient(160deg, var(--app-icon-from), var(--app-icon-to));
}
.app-icon-material-metal .app-icon-base {
  background:
    linear-gradient(135deg, rgba(255,255,255,.42), transparent 36%),
    linear-gradient(160deg, var(--app-icon-from), var(--app-icon-to));
}
.app-icon-material-glass .app-icon-base {
  background:
    radial-gradient(circle at 30% 20%, rgba(255,255,255,.42), transparent 40%),
    linear-gradient(160deg, color-mix(in srgb, var(--app-icon-from) 88%, white), var(--app-icon-to));
}
.app-icon-material-glass .app-icon-rim {
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,.42),
    inset 0 0 12px rgba(255,255,255,.16);
}
.app-icon-sm .app-icon-sheen { inset: 0 0 50%; }
.app-icon-sm .app-icon-base {
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.45),
    0 1px 2px rgba(0,0,0,.2),
    0 3px 8px rgba(0,0,0,.16);
}
</style>
