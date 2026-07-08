<template>
  <div class="tool-progress-row">
    <button class="tool-progress-toggle" @click="isOpen = !isOpen">
      <span class="tool-progress-dot" :class="stateClass"></span>
      <span class="tool-progress-title">{{ title }}</span>
      <span v-if="durationText" class="tool-progress-duration">{{ durationText }}</span>
      <svg class="tool-progress-chevron" :class="{ rotated: isOpen }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
        <path d="M4 3l4 3-4 3" />
      </svg>
    </button>
    <div v-show="isOpen" class="tool-progress-body">
      <div v-if="tools.length" class="tool-progress-tools">
        <div v-for="tool in tools" :key="tool.tool_call_id || tool.effective_tool_name || tool.name" class="tool-progress-tool">
          <span class="tool-progress-tool-name" :title="displayToolName(tool)">{{ displayToolName(tool) }}</span>
        </div>
      </div>
      <div v-if="nodes.length" class="tool-progress-nodes">
        <div v-for="(node, index) in nodes" :key="`${node.toolCallId || node.toolName || index}-${node.node}-${node.status}`" class="tool-progress-node">
          <span class="tool-progress-node-dot" :class="node.status"></span>
          <span class="tool-progress-node-name">{{ nodeTitle(node) }}</span>
          <span class="tool-progress-node-status">{{ statusText(node.status) }}</span>
          <span v-if="node.elapsedMs" class="tool-progress-node-time">{{ formatDuration(node.elapsedMs) }}</span>
        </div>
      </div>
      <div v-if="!tools.length && !nodes.length" class="tool-progress-empty">等待工具节点返回</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type ToolInfo = {
  name?: string
  effective_tool_name?: string
  tool_call_id?: string
}

type ToolProgressMessage = {
  executionMode?: string
  groupIndex?: number
  groupCount?: number
  toolCount?: number
  toolName?: string
  toolCallId?: string
  toolNodes?: ToolProgressMessage[]
  node?: string
  status?: string
  targetTool?: string
  elapsedMs?: number
  durationMs?: number
  tools?: ToolInfo[]
}

const props = defineProps<{
  message: ToolProgressMessage
}>()

const isOpen = ref(true)

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  skill_list: '查看技能列表',
  skill_describe: '查看技能说明',
  skill_use: '调用技能',
  knowledge__search: '检索知识库',
  knowledge__get_block: '读取知识块',
  web_tools__search: '联网搜索',
}

const tools = computed<ToolInfo[]>(() => props.message.tools || [])
const nodes = computed<ToolProgressMessage[]>(() => props.message.toolNodes || [])

const title = computed(() => {
  const mode = props.message.executionMode === 'parallel' ? '并行工具组' : '串行工具组'
  const count = props.message.toolCount || tools.value.length || 1
  const indexText = props.message.groupIndex && props.message.groupCount
    ? ` ${props.message.groupIndex}/${props.message.groupCount}`
    : ''
  return `${mode}${indexText} · ${count} 个工具`
})

const stateClass = computed(() => {
  if (nodes.value.some(node => node.status === 'timeout' || node.status === 'failed')) return 'failed'
  if (nodes.value.some(node => node.status === 'started')) return 'running'
  return 'ready'
})

const durationText = computed(() => {
  const ms = props.message.durationMs || props.message.elapsedMs || 0
  return ms ? `· ${formatDuration(ms)}` : ''
})

watch(
  () => props.message.executionMode,
  mode => { isOpen.value = mode === 'parallel' || nodes.value.length > 0 },
  { immediate: true },
)

function displayToolName(tool: ToolInfo): string {
  const name = tool.effective_tool_name || tool.name || 'unknown'
  return TOOL_DISPLAY_NAMES[name] || name
}

function nodeTitle(node: ToolProgressMessage): string {
  const toolName = node.targetTool || node.toolName || ''
  const nodeName = node.node || 'tool_node'
  if (toolName && toolName !== node.toolName) return `${nodeName} · ${toolName}`
  return nodeName
}

function statusText(status?: string): string {
  if (status === 'started') return '开始'
  if (status === 'completed') return '完成'
  if (status === 'timeout') return '超时'
  if (status === 'failed') return '失败'
  if (status === 'blocked') return '已拦截'
  return status || '处理中'
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`
  const sec = ms / 1000
  if (sec < 60) return `${Number(sec.toFixed(sec < 10 ? 1 : 0))}秒`
  const minutes = Math.floor(sec / 60)
  const rest = Math.round(sec % 60)
  return `${minutes}分${rest}秒`
}
</script>

<style scoped>
.tool-progress-row {
  flex-shrink: 0;
  align-self: flex-start;
  max-width: 95%;
  margin-bottom: var(--ag-space-sm);
}

.tool-progress-toggle {
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
.tool-progress-toggle:hover { color: var(--ag-text-secondary); }

.tool-progress-dot,
.tool-progress-node-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--ag-radius-full);
  flex-shrink: 0;
}
.tool-progress-dot.ready { background: var(--ag-text-disabled); }
.tool-progress-dot.running {
  background: var(--ag-primary);
  animation: toolProgressPulse 1.6s ease-out infinite;
}
.tool-progress-dot.failed { background: var(--ag-error); }
@keyframes toolProgressPulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.tool-progress-title {
  color: var(--ag-text-secondary);
  font-weight: 500;
}
.tool-progress-duration,
.tool-progress-node-time {
  font-size: 11px;
  color: var(--ag-text-disabled);
}
.tool-progress-chevron {
  transition: transform var(--ag-transition-base);
  flex-shrink: 0;
}
.tool-progress-chevron.rotated { transform: rotate(90deg); }

.tool-progress-body {
  margin-top: var(--ag-space-xs);
  padding: var(--ag-space-xs) 0 var(--ag-space-xs) var(--ag-space-md);
  border-left: 1px solid var(--ag-border-light);
}
.tool-progress-tools,
.tool-progress-nodes {
  display: grid;
  gap: 4px;
}
.tool-progress-tools + .tool-progress-nodes { margin-top: var(--ag-space-xs); }
.tool-progress-tool,
.tool-progress-node {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 18px;
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-secondary);
}
.tool-progress-tool-name {
  font-family: var(--ag-font-mono);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tool-progress-node-dot {
  width: 5px;
  height: 5px;
  background: var(--ag-text-disabled);
  opacity: 0.7;
}
.tool-progress-node-dot.started { background: var(--ag-primary); }
.tool-progress-node-dot.completed { background: var(--ag-success); }
.tool-progress-node-dot.timeout,
.tool-progress-node-dot.failed { background: var(--ag-error); }
.tool-progress-node-name {
  font-family: var(--ag-font-mono);
  color: var(--ag-text-primary);
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tool-progress-node-status {
  color: var(--ag-text-tertiary);
  flex-shrink: 0;
}
.tool-progress-node-time { margin-left: auto; }
.tool-progress-empty {
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-disabled);
}
</style>
