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
        <div v-else-if="item.eventType === 'planner_status'" class="work-planner-status-row">
          <span class="work-plan-dot"></span>
          <span>{{ item.plannerMessage || '正在分析任务并制定执行步骤…' }}</span>
          <span v-if="item.planRound && item.planRound > 1">（第{{ item.planRound }}轮）</span>
        </div>
        <div v-else-if="item.eventType === 'action_plan'" class="work-plan-row">
          <div class="work-plan-label">
            <span class="work-plan-dot"></span>
            <span>{{ item.plannerMessage || '已制定执行步骤，准备开始执行' }}<span v-if="item.planRound && item.planRound > 1">（第{{ item.planRound }}轮）</span></span>
          </div>
          <div v-if="item.planGoal" class="work-plan-goal">{{ item.planGoal }}</div>
          <div v-if="item.planActions?.length" class="work-plan-actions">
            <div v-for="action in item.planActions" :key="action.id || action.capability" class="work-plan-action">
              {{ displayCapability(action.capability || '') }}
            </div>
          </div>
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
          <div class="work-draft-label">
            <span class="work-draft-label-icon" aria-hidden="true"></span>
            <span>{{ item.title || '回复用户' }}</span>
            <span v-if="item.reason" class="work-draft-reason">{{ draftReasonText(item.reason) }}</span>
          </div>
          <div class="work-draft-bubble">
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
  plannerPhase?: string
  plannerMessage?: string
  planRound?: number
  planGoal?: string
  planActions?: Array<{ id?: string; capability?: string }>
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

function draftReasonText(reason: string): string {
  if (reason === 'tool_call_detected') return '工具调用前回复'
  if (reason === 'rollback') return '回退前草稿'
  if (reason === 'replace') return '被后续回复替换'
  return reason
}

function displayCapability(capability: string): string {
  const [, action = capability] = capability.split('__', 2)
  const labels: Record<string, string> = {
    list_files: '列出文件',
    get_file_content: '读取文件',
    search: '搜索内容',
    generate: '生成内容',
  }
  return labels[action] || action.replace(/_/g, ' ') || '执行操作'
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

.work-planner-status-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-sm);
}

.work-plan-row {
  display: grid;
  gap: var(--ag-space-xs);
  padding: var(--ag-space-xs) 0 var(--ag-space-sm);
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-sm);
}
.work-plan-label {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--ag-text-secondary);
}
.work-plan-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--ag-radius-full);
  background: var(--ag-primary);
  flex-shrink: 0;
}
.work-plan-goal {
  color: var(--ag-text-tertiary);
  line-height: var(--ag-line-height-base);
}
.work-plan-actions {
  display: grid;
  gap: 2px;
  color: var(--ag-text-disabled);
  font-size: var(--ag-font-size-xs);
}
.work-plan-action::before { content: '·'; margin-right: 5px; }

.work-draft-row {
  display: grid;
  gap: var(--ag-space-xs);
  padding: var(--ag-space-xs) 0 var(--ag-space-sm);
}
.work-draft-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  width: fit-content;
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-xs);
}
.work-draft-label-icon {
  width: 6px;
  height: 6px;
  border-radius: var(--ag-radius-full);
  background: var(--ag-primary);
  opacity: 0.75;
}
.work-draft-reason {
  font-size: 11px;
  color: var(--ag-text-disabled);
}
.work-draft-bubble {
  max-width: min(560px, 100%);
  width: fit-content;
  padding: var(--ag-space-md) var(--ag-space-lg);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm) var(--ag-radius-xl) var(--ag-radius-xl) var(--ag-radius-xl);
  background: var(--ag-bg-assistant-msg);
  box-shadow: var(--ag-shadow-sm);
}
.work-draft-content {
  font-size: var(--ag-font-size-md);
  color: var(--ag-text-primary);
  line-height: var(--ag-line-height-relaxed);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}
</style>
