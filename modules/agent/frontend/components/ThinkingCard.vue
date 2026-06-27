<template>
  <div class="thinking-row">
    <button class="th-toggle" @click="isOpen = !isOpen">
      <span class="th-dot" :class="{ running: running }"></span>
      <span>思维过程</span>
      <span v-if="showSpinner" class="th-spinner"></span>
      <span v-else-if="durationText" class="th-duration">{{ durationText }}</span>
      <svg class="th-chevron" :class="{ rotated: isOpen }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
        <path d="M4 3l4 3-4 3"/>
      </svg>
    </button>
    <div v-show="isOpen" class="th-body">
      <span v-if="running && !displayedContent" class="th-waiting">思考中…</span>
      <template v-else>{{ displayedContent }}</template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'

const props = defineProps<{ content: string; running?: boolean; collapsed?: boolean; durationMs?: number }>()
const isOpen = ref(!props.collapsed)

let typeTimer: ReturnType<typeof setInterval> | null = null
const displayedContent = ref('')

// 逐字打字效果：当 content 增长时，逐字追加到 displayedContent
watch(
  () => props.content,
  (newVal) => {
    if (!props.running) {
      // 已完成状态：直接显示全部
      stopTypeTimer()
      displayedContent.value = normalize(newVal)
      return
    }
    // 运行中：逐字追加
    const normalized = normalize(newVal)
    if (normalized.length <= displayedContent.value.length) return
    startTypeTimer(normalized)
  },
  { immediate: true }
)

watch(
  () => props.running,
  (r) => {
    if (!r) {
      stopTypeTimer()
      displayedContent.value = normalize(props.content)
    }
  }
)

function startTypeTimer(full: string) {
  if (typeTimer) return
  typeTimer = setInterval(() => {
    const pos = displayedContent.value.length
    if (pos < full.length) {
      displayedContent.value = full.slice(0, pos + 1)
    } else {
      stopTypeTimer()
    }
  }, 20)
}

function stopTypeTimer() {
  if (typeTimer) { clearInterval(typeTimer); typeTimer = null }
}

onUnmounted(() => stopTypeTimer())

/** 去掉换行符，压缩连续空格，不引入新空格 */
function normalize(text: string): string {
  return text.replace(/[\n\r]+/g, '').replace(/[ \t]{2,}/g, ' ').trim()
}

const showSpinner = computed(() => props.running && displayedContent.value.length < 10)
const durationText = computed(() => {
  if (props.running) return ''
  if (!props.durationMs) return ''
  if (props.durationMs < 1000) return `· ${props.durationMs}ms`
  const sec = props.durationMs / 1000
  if (sec < 60) return `· ${Number(sec.toFixed(sec < 10 ? 1 : 0))}秒`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `· ${m}分${s}秒`
})
</script>

<style scoped>
.thinking-row {
  flex-shrink: 0;
  align-self: flex-start;
  max-width: 85%;
  margin-bottom: var(--ag-space-sm);
  animation: msgSlideUp 0.25s ease-out;
}
@keyframes msgSlideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.th-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-tertiary);
  padding: 2px 0;
  transition: color var(--ag-transition-fast);
}
.th-toggle:hover { color: var(--ag-text-secondary); }

.th-duration { font-size: 11px; color: var(--ag-text-disabled); }

.th-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--ag-radius-full);
  background: var(--ag-warning);
  flex-shrink: 0;
}
.th-dot.running {
  animation: thPulse 1.6s ease-out infinite;
}
@keyframes thPulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.th-spinner {
  width: 12px; height: 12px;
  border: 2px solid var(--ag-border-light);
  border-top-color: var(--ag-primary);
  border-radius: 50%;
  animation: thSpin 0.8s linear infinite;
}
@keyframes thSpin { to { transform: rotate(360deg); } }

.th-chevron {
  transition: transform var(--ag-transition-base);
}
.th-chevron.rotated { transform: rotate(90deg); }

.th-body {
  margin-top: var(--ag-space-xs);
  padding: var(--ag-space-sm) var(--ag-space-md);
  background: var(--ag-bg-page);
  border-radius: var(--ag-radius-md);
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-secondary);
  line-height: var(--ag-line-height-base);
  white-space: pre-wrap;
  word-break: break-word;
}

.th-waiting { color: var(--ag-text-disabled); font-style: italic; }
</style>
