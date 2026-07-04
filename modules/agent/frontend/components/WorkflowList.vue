<template>
  <section class="workflow-panel">
    <header class="workflow-panel__header">
      <div>
        <h2>工作流</h2>
        <span>{{ totalLabel }}</span>
      </div>
      <button type="button" class="workflow-refresh" :disabled="loading" @click="loadWorkflows">刷新</button>
    </header>

    <div v-if="error" class="workflow-panel__error">{{ error }}</div>

    <div class="workflow-panel__body">
      <aside class="workflow-list">
        <div v-if="loading" class="workflow-list__state">加载中...</div>
        <div v-else-if="workflows.length === 0" class="workflow-list__state">暂无工作流</div>
        <button
          v-for="workflow in workflows"
          :key="workflow.id"
          type="button"
          class="workflow-card"
          :class="{ active: workflow.id === selectedId }"
          @click="selectedId = workflow.id"
        >
          <div class="workflow-card__top">
            <span class="workflow-card__title">{{ workflow.title }}</span>
            <WorkflowStatusBadge :status="workflow.status" />
          </div>
          <p>{{ workflow.progress_summary || '暂无进度摘要' }}</p>
          <div class="workflow-card__meta">
            <span>{{ workflowNeedsConfirmation(workflow) ? '需要确认' : '无需确认' }}</span>
            <span v-if="multiAgentSummaryCount(workflow) > 0">子代理/步骤 {{ multiAgentSummaryCount(workflow) }}</span>
            <span>{{ formatDateTime(workflow.updated_at) }}</span>
          </div>
        </button>
      </aside>

      <WorkflowDetail
        class="workflow-panel__detail"
        :run-id="selectedId"
        :summary="selectedWorkflow"
        :is-admin="isAdmin"
        @open-approvals="$emit('openApprovals')"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { apiGet } from '../api'
import WorkflowDetail from './WorkflowDetail.vue'
import WorkflowStatusBadge from './WorkflowStatusBadge.vue'
import type { MultiAgentSummarySource, WorkflowListResponse, WorkflowSummary } from './workflowTypes'

withDefaults(defineProps<{
  isAdmin?: boolean
}>(), {
  isAdmin: false,
})

defineEmits<{
  openApprovals: []
}>()

const loading = ref(false)
const error = ref('')
const workflows = ref<WorkflowSummary[]>([])
const selectedId = ref<number | null>(null)

const selectedWorkflow = computed(() => workflows.value.find(item => item.id === selectedId.value) || null)
const totalLabel = computed(() => workflows.value.length ? `${workflows.value.length} 个任务` : '无任务')

onMounted(loadWorkflows)

async function loadWorkflows() {
  loading.value = true
  error.value = ''
  try {
    const payload = await apiGet<WorkflowListResponse>('/agent/workflows')
    workflows.value = normalizeWorkflowList(payload)
    if (!selectedId.value || !workflows.value.some(item => item.id === selectedId.value)) {
      selectedId.value = workflows.value[0]?.id ?? null
    }
  } catch (caught: unknown) {
    workflows.value = []
    selectedId.value = null
    error.value = readableError(caught)
  } finally {
    loading.value = false
  }
}

function normalizeWorkflowList(payload: WorkflowListResponse): WorkflowSummary[] {
  return Array.isArray(payload) ? payload : payload.items ?? []
}

function workflowNeedsConfirmation(workflow: WorkflowSummary): boolean {
  return Boolean(workflow.needs_confirmation || workflow.status === 'needs_confirmation')
}

function multiAgentSummaryCount(workflow: WorkflowSummary): number {
  return countMultiAgentSummary(workflow.multi_agent_summary)
}

function countMultiAgentSummary(source: MultiAgentSummarySource | undefined): number {
  if (!source) return 0
  return Array.isArray(source) ? source.length : source.items?.length ?? 0
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function readableError(caught: unknown): string {
  const message = caught instanceof Error ? caught.message : String(caught)
  if (message.includes('404') || message.includes('Unexpected token')) {
    return '工作流接口暂未可用'
  }
  return message || '加载失败'
}
</script>

<style scoped>
.workflow-panel {
  height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--ag-bg-page);
  color: var(--ag-text-primary);
}
.workflow-panel__header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ag-space-lg);
  padding: var(--ag-space-xl) var(--ag-space-2xl);
  border-bottom: 1px solid var(--ag-border-light);
  background: var(--ag-bg-base);
}
.workflow-panel__header h2 {
  margin: 0;
  font-size: 18px;
  line-height: var(--ag-line-height-tight);
}
.workflow-panel__header span {
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-sm);
}
.workflow-refresh {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--ag-border-base);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-text-secondary);
  cursor: pointer;
  font-size: var(--ag-font-size-sm);
}
.workflow-refresh:hover:not(:disabled) {
  border-color: var(--ag-primary);
  color: var(--ag-primary);
}
.workflow-refresh:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.workflow-panel__error {
  flex-shrink: 0;
  padding: var(--ag-space-sm) var(--ag-space-2xl);
  color: var(--ag-error);
  background: #fff0ee;
  border-bottom: 1px solid #fac5bf;
  font-size: var(--ag-font-size-sm);
}
.workflow-panel__body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(280px, 34%) minmax(0, 1fr);
}
.workflow-list {
  min-width: 0;
  overflow-y: auto;
  padding: var(--ag-space-lg);
  border-right: 1px solid var(--ag-border-light);
  background: var(--ag-bg-sidebar);
}
.workflow-list__state {
  padding: var(--ag-space-3xl);
  color: var(--ag-text-tertiary);
  text-align: center;
  font-size: var(--ag-font-size-base);
}
.workflow-card {
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-sm);
  margin-bottom: var(--ag-space-sm);
  padding: var(--ag-space-md);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-md);
  background: var(--ag-bg-base);
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color var(--ag-transition-fast), background var(--ag-transition-fast), box-shadow var(--ag-transition-fast);
}
.workflow-card:hover {
  border-color: var(--ag-primary);
  box-shadow: var(--ag-shadow-sm);
}
.workflow-card.active {
  border-color: var(--ag-primary);
  background: var(--ag-primary-light);
}
.workflow-card__top {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ag-space-sm);
}
.workflow-card__title {
  min-width: 0;
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-md);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workflow-card p {
  margin: 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-sm);
  line-height: var(--ag-line-height-base);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.workflow-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ag-space-sm);
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-xs);
}
.workflow-panel__detail {
  min-width: 0;
  overflow-y: auto;
  padding: var(--ag-space-xl);
}
@media (max-width: 840px) {
  .workflow-panel__body {
    grid-template-columns: 1fr;
  }
  .workflow-list {
    max-height: 42%;
    border-right: none;
    border-bottom: 1px solid var(--ag-border-light);
  }
}
</style>
