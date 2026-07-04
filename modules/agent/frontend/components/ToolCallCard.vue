<template>
  <div class="tool-row">
	    <button class="tool-toggle" @click="isOpen = !isOpen">
	      <span class="tool-dot" :class="toolState"></span>
	      <template v-if="message.eventType === 'tool_call'">
	        <span>正在调用</span>
	        <span class="tool-name" :title="message.toolName">{{ displayToolName }}</span>
        <span class="tool-calling-dots">
          <span class="cdot"></span><span class="cdot"></span><span class="cdot"></span>
        </span>
	      </template>
		      <template v-else>
		        <span>{{ statusText }}</span>
		        <span class="tool-name" :title="message.toolName">{{ displayToolName }}</span>
		        <span v-if="durationText" class="tool-duration">{{ durationText }}</span>
	        <svg class="tool-chevron" :class="{ rotated: isOpen }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
          <path d="M4 3l4 3-4 3"/>
        </svg>
      </template>
	    </button>
	    <div v-show="isOpen && message.eventType === 'tool_result'" class="tool-body">
	      <div v-if="errorText" class="tool-error">{{ errorText }}</div>
	      <EvidenceReferenceList v-if="referenceList.length" :references="referenceList" dense class="tool-refs" />
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
import { apiFetchRaw } from '../api'
import EvidenceReferenceList from './EvidenceReferenceList.vue'
import {
  collectEvidenceReferences,
  type EvidenceReference,
} from './evidenceReferences'

const props = defineProps<{
  message: {
	    eventType?: string
	    toolName?: string
	    toolResult?: unknown
	    toolStatus?: string
	    toolError?: string
	    toolReferences?: EvidenceReference[]
	    durationMs?: number
	  }
	}>()

const isOpen = ref(false)

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  skill_list: '查看技能列表',
  skill_describe: '查看技能说明',
  skill_use: '调用技能',
  'docs-open__open': '打开文档',
  'docs-open__get_content': '获取文档内容',
  'docs-open__create_doc': '创建文档',
  'media-asr__extract_audio': '提取视频音频',
  'media-asr__transcribe_audio': '音频转文字',
  'media-asr__transcribe_video': '视频转文字',
}

const displayToolName = computed(() => {
  const name = props.message.toolName || ''
  return TOOL_DISPLAY_NAMES[name] || name || '未知工具'
})

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
  if (Array.isArray(obj.images) && obj.images.some(isImageEntry)) return true
  if (isImageEntry(obj)) return true
  return false
}

function extractImages(r: unknown): ImageEntry[] {
  if (!r || typeof r !== 'object') return []
  const obj = r as Record<string, unknown>
  if (Array.isArray(obj.images)) {
    return obj.images.filter(isImageEntry)
  }
  if (isImageEntry(obj)) {
    return [obj]
  }
  return []
}

function isImageEntry(value: unknown): value is ImageEntry {
  if (!isRecord(value)) return false
  if (value.type !== undefined && value.type !== 'image') return false
  return typeof value.file_id === 'number'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function resultPayload(result: unknown): unknown {
  if (!isRecord(result)) return result
  const data = result.data
  return isRecord(data) ? data : result
}

function isFailureResult(result: unknown): boolean {
  if (props.message.toolStatus === 'failed') return true
  if (!isRecord(result)) return false
  if (result.success === false || result.error || result.denied || result.policy_blocked) return true
  const inner = resultPayload(result)
  return isRecord(inner) && (inner.success === false || !!inner.error)
}

const toolState = computed(() => {
  if (props.message.eventType === 'tool_call') return 'calling'
  return isFailureResult(props.message.toolResult) ? 'failed' : 'done'
})

const statusText = computed(() => {
  if (props.message.eventType === 'tool_call') return '正在调用'
  return toolState.value === 'failed' ? '工具失败' : '工具完成'
})

const errorText = computed(() => {
  if (toolState.value !== 'failed') return ''
  if (props.message.toolError) return props.message.toolError
  const result = props.message.toolResult
  if (!isRecord(result)) return ''
  const inner = resultPayload(result)
  const message = result.error || result.message || (isRecord(inner) ? (inner.error || inner.message) : '')
  return typeof message === 'string' ? message : ''
})

const referenceList = computed<EvidenceReference[]>(() => {
  if (props.message.toolReferences?.length) return props.message.toolReferences
  return collectEvidenceReferences(props.message.toolResult, {
    sourceTool: props.message.toolName,
    status: props.message.toolStatus,
  })
})

function formatResult(r: unknown): string {
  if (typeof r === 'string') return r
  try { return JSON.stringify(r, null, 2) } catch { return String(r) }
}

async function openImage(fileId: number) {
  try {
    const response = await apiFetchRaw(`/files/download/${fileId}`)
    if (!response.ok) throw new Error(`文件下载接口返回 ${response.status}`)
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    window.open(objectUrl, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  } catch (error: unknown) {
    console.warn('[agent] open image failed', error)
  }
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
.tool-dot.failed {
  background: var(--ag-error);
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
.tool-error {
  margin-bottom: var(--ag-space-xs);
  color: var(--ag-error);
  font-size: var(--ag-font-size-sm);
  line-height: var(--ag-line-height-base);
  word-break: break-word;
}
.tool-refs { margin-bottom: var(--ag-space-xs); }
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
