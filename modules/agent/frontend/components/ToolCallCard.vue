<template>
  <div class="tool-row">
    <button class="tool-toggle" @click="isOpen = !isOpen">
      <span class="tool-dot" :class="{ calling: message.eventType === 'tool_call', done: message.eventType === 'tool_result' }"></span>
      <template v-if="message.eventType === 'tool_call'">
        <span>正在调用</span>
        <span class="tool-name">{{ message.toolName }}</span>
        <span class="tool-calling-dots">
          <span class="cdot"></span><span class="cdot"></span><span class="cdot"></span>
        </span>
      </template>
	      <template v-else>
	        <span>工具记录</span>
	        <span class="tool-name">{{ message.toolName }}</span>
	        <span v-if="durationText" class="tool-duration">{{ durationText }}</span>
	        <svg class="tool-chevron" :class="{ rotated: isOpen }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
          <path d="M4 3l4 3-4 3"/>
        </svg>
      </template>
    </button>
    <div v-show="isOpen && message.eventType === 'tool_result'" class="tool-body">
      <template v-if="hasImage(message.toolResult)">
        <div class="tool-images">
          <img
            v-for="img in extractImages(message.toolResult)"
            :key="img.file_id"
            :src="`/api/files/download/${img.file_id}`"
            class="tool-image"
            :alt="img.name || '生成图片'"
            @click="openImage(img.file_id)"
          />
        </div>
      </template>
      <pre v-else>{{ formatResult(message.toolResult) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  message: {
    eventType?: string
    toolName?: string
    toolResult?: unknown
    durationMs?: number
  }
}>()

const isOpen = ref(false)

const durationText = computed(() => {
  if (props.message.eventType !== 'tool_result') return ''
  const ms = props.message.durationMs
  if (!ms) return ''
  if (ms < 1000) return `· ${ms}ms`
  const sec = ms / 1000
  if (sec < 60) return `· ${Number(sec.toFixed(sec < 10 ? 1 : 0))}秒`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `· ${m}分${s}秒`
})

interface ImageEntry {
  type?: string
  file_id: number
  name?: string
  [key: string]: unknown
}

function hasImage(r: unknown): boolean {
  if (!r || typeof r !== 'object') return false
  const obj = r as Record<string, unknown>
  if (Array.isArray(obj.images) && obj.images.length > 0) return true
  if (obj.type === 'image' && typeof obj.file_id === 'number') return true
  return false
}

function extractImages(r: unknown): ImageEntry[] {
  if (!r || typeof r !== 'object') return []
  const obj = r as Record<string, unknown>
  if (Array.isArray(obj.images)) {
    return obj.images as ImageEntry[]
  }
  if (obj.type === 'image' && typeof obj.file_id === 'number') {
    return [obj as unknown as ImageEntry]
  }
  return []
}

function formatResult(r: unknown): string {
  if (typeof r === 'string') return r
  try { return JSON.stringify(r, null, 2) } catch { return String(r) }
}

function openImage(fileId: number) {
  const url = `/api/files/download/${fileId}`
  window.open(url, '_blank')
}
</script>

<style scoped>
	.tool-row {
	  flex-shrink: 0;
	  align-self: flex-start;
	  max-width: 95%;
	  margin-bottom: var(--ag-space-sm);
	  animation: msgSlideUp 0.25s ease-out;
	}
	@keyframes msgSlideUp {
	  from { opacity: 0; transform: translateY(10px); }
	  to { opacity: 1; transform: translateY(0); }
	}

	.tool-toggle {
	  display: flex;
	  align-items: center;
	  gap: 5px;
	  white-space: nowrap;
	  border: none;
  background: none;
  cursor: pointer;
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-tertiary);
  padding: 2px 0;
  transition: color var(--ag-transition-fast);
}
.tool-toggle:hover { color: var(--ag-text-secondary); }

.tool-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--ag-radius-full);
  flex-shrink: 0;
  background: var(--ag-text-disabled);
}
.tool-dot.calling {
  background: #1677FF;
  animation: toolPulse 1.6s ease-out infinite;
}
.tool-dot.done {
  background: var(--ag-success);
}
@keyframes toolPulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.tool-name {
  color: var(--ag-text-primary);
  font-family: var(--ag-font-mono);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-duration { font-size: 11px; color: var(--ag-text-disabled); flex-shrink: 0; }

.tool-calling-dots { display: inline-flex; gap: 2px; align-items: center; }
.tool-calling-dots .cdot {
  width: 3px; height: 3px; border-radius: var(--ag-radius-full);
  background: #1677FF;
  animation: toolDot 1.2s ease-in-out infinite;
}
.tool-calling-dots .cdot:nth-child(2) { animation-delay: 0.2s; }
.tool-calling-dots .cdot:nth-child(3) { animation-delay: 0.4s; }
@keyframes toolDot { 0%, 100% { opacity: 0.3; transform: scale(1); } 50% { opacity: 1; transform: scale(1.3); } }

.tool-chevron {
  transition: transform var(--ag-transition-base);
  flex-shrink: 0;
}
.tool-chevron.rotated { transform: rotate(90deg); }

.tool-body {
  margin-top: var(--ag-space-xs);
  padding: var(--ag-space-sm) var(--ag-space-md);
  background: var(--ag-bg-page);
  border-radius: var(--ag-radius-md);
}
.tool-body pre {
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow: auto;
  font-size: var(--ag-font-size-sm);
  font-family: var(--ag-font-mono);
  color: var(--ag-text-secondary);
  margin: 0;
}

.tool-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-image {
  max-width: 320px;
  max-height: 240px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--ag-border-light, #e5e5e5);
  transition: transform 0.15s ease;
  object-fit: contain;
  background: #f8f8f8;
}

.tool-image:hover {
  transform: scale(1.03);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
</style>
