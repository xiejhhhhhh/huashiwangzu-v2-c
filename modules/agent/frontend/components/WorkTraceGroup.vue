<template>
  <div class="work-group-row">
    <button class="work-group-toggle" @click="isOpen = !isOpen">
      <span class="work-group-dot" :class="{ running: message.running }"></span>
      <span>{{ title }}</span>
      <svg class="work-group-chevron" :class="{ rotated: isOpen }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
        <path d="M4 3l4 3-4 3" />
      </svg>
    </button>

    <div v-show="isOpen" class="work-group-body">
      <template v-for="(item, index) in message.items || []" :key="`${item.eventType}-${index}`">
        <div v-if="item.eventType === 'schedule_overhead'" class="work-overhead-row">
          <span class="work-overhead-dot"></span>
          <span>{{ item.label || '响应等待' }}</span>
          <span class="work-overhead-time">{{ formatDuration(item.durationMs || 0) }}</span>
        </div>
        <ThinkingCard
          v-else-if="item.eventType === 'thinking'"
          :content="item.content"
          :running="item.running"
          :collapsed="item.collapsed"
          :durationMs="item.durationMs"
        />
        <ToolCallCard
          v-else-if="item.eventType === 'tool_call' || item.eventType === 'tool_result'"
          :message="item"
        />
        <ToolProgressCard
          v-else-if="item.eventType === 'tool_progress'"
          :message="item"
        />
        <div v-else-if="item.eventType === 'assistant_draft'" class="work-draft-row">
          <button class="work-draft-toggle" @click="toggleDraft(index)">
            <span class="work-draft-icon">💬</span>
            <span class="work-draft-title">{{ item.title || '回复用户' }}</span>
            <span v-if="item.reason" class="work-draft-reason">{{ item.reason }}</span>
            <svg class="work-draft-chevron" :class="{ rotated: draftOpen[index] }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
              <path d="M4 3l4 3-4 3" />
            </svg>
          </button>
          <div v-show="draftOpen[index]" class="work-draft-body">
            <div class="work-draft-content">{{ item.content }}</div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ThinkingCard from './ThinkingCard.vue'
import ToolCallCard from './ToolCallCard.vue'
import ToolProgressCard from './ToolProgressCard.vue'

interface TraceItem {
  eventType?: string
  role: string
  content: string
  running?: boolean
  collapsed?: boolean
  durationMs?: number
  toolName?: string
  toolResult?: unknown
  toolStatus?: string
  toolError?: string
  toolCallId?: string
  executionMode?: string
  groupIndex?: number
  groupCount?: number
  toolCount?: number
  tools?: Array<{ name?: string; effective_tool_name?: string; tool_call_id?: string }>
  toolNodes?: TraceItem[]
  node?: string
  status?: string
  targetTool?: string
  elapsedMs?: number
  label?: string
  title?: string
  reason?: string
}

const props = defineProps<{
  message: {
    running?: boolean
    collapsed?: boolean
    durationMs?: number
    items?: TraceItem[]
  }
}>()

const isOpen = ref(!props.message.collapsed)
const draftOpen = ref<Record<number, boolean>>({})

function toggleDraft(index: number) {
  draftOpen.value[index] = !draftOpen.value[index]
}

watch(
  () => props.message.collapsed,
  collapsed => { isOpen.value = !collapsed },
)

const title = computed(() => {
  const prefix = props.message.running ? '正在工作' : '已工作'
  return `${prefix} ${formatDuration(props.message.durationMs || 0)}`
})

function formatDuration(ms: number): string {
  const sec = ms / 1000
  if (sec < 1) return '0秒'
  if (sec < 60) return `${Math.floor(sec)}秒`
  const minutes = Math.floor(sec / 60)
  const rest = Math.round(sec % 60)
  return `${minutes}分${rest}秒`
}
</script>

<style scoped>
.work-group-row {
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

.work-group-toggle {
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
.work-group-toggle:hover { color: var(--ag-text-secondary); }

.work-group-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--ag-radius-full);
  background: var(--ag-success);
  flex-shrink: 0;
}
.work-group-dot.running {
  background: var(--ag-primary);
  animation: workPulse 1.6s ease-out infinite;
}
@keyframes workPulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.work-group-chevron { transition: transform var(--ag-transition-base); }
.work-group-chevron.rotated { transform: rotate(90deg); }

.work-group-body {
  margin-top: var(--ag-space-xs);
  padding-left: var(--ag-space-md);
  border-left: 1px solid var(--ag-border-light);
}

.work-overhead-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-disabled);
}
.work-overhead-dot {
  width: 4px; height: 4px;
  border-radius: var(--ag-radius-full);
  background: var(--ag-text-disabled);
  flex-shrink: 0;
  opacity: 0.5;
}
.work-overhead-time { margin-left: auto; font-size: 11px; }

.work-draft-row {
  padding: 2px 0;
}
.work-draft-toggle {
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
  width: 100%;
  text-align: left;
}
.work-draft-toggle:hover { color: var(--ag-text-secondary); }
.work-draft-icon { flex-shrink: 0; font-size: 12px; }
.work-draft-title { font-weight: 500; }
.work-draft-reason {
  font-size: 11px;
  color: var(--ag-text-disabled);
  margin-left: auto;
}
.work-draft-chevron {
  flex-shrink: 0;
  transition: transform var(--ag-transition-base);
}
.work-draft-chevron.rotated { transform: rotate(90deg); }
.work-draft-body {
  padding: 4px 0 4px 18px;
}
.work-draft-content {
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-secondary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--ag-bg-secondary);
  border-radius: var(--ag-radius-sm);
  padding: 6px 8px;
}
</style>
