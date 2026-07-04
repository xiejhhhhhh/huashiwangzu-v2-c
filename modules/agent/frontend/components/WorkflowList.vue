<template>
  <section class="workflow-panel">
    <header class="workflow-panel__header">
      <div>
        <h2>工作流</h2>
        <span>{{ totalLabel }}</span>
      </div>
      <button type="button" class="workflow-refresh" :disabled="loading" @click="refreshAll">刷新</button>
    </header>

    <div class="workflow-summary">
      <div>
        <span>总数</span>
        <strong>{{ governanceSummary?.total ?? workflows.length }}</strong>
      </div>
      <div>
        <span>失败</span>
        <strong>{{ governanceSummary?.failed ?? 0 }}</strong>
      </div>
      <div>
        <span>待确认</span>
        <strong>{{ governanceSummary?.needs_confirmation ?? 0 }}</strong>
      </div>
      <div>
        <span>有产物</span>
        <strong>{{ governanceSummary?.with_artifacts ?? 0 }}</strong>
      </div>
      <div>
        <span>有引用</span>
        <strong>{{ governanceSummary?.with_references ?? 0 }}</strong>
      </div>
    </div>

    <div class="workflow-filters" role="tablist" aria-label="workflow filters">
      <button
        v-for="option in filterOptions"
        :key="option.key"
        type="button"
        :class="{ active: activeFilter === option.key }"
        @click="selectFilter(option.key)"
      >
        {{ option.label }}
      </button>
    </div>

    <div v-if="error" class="workflow-panel__error">{{ error }}</div>

    <div class="workflow-panel__body">
      <aside class="workflow-list">
        <div v-if="loading" class="workflow-list__state">加载中...</div>
        <div v-else-if="!error && workflows.length === 0" class="workflow-list__state">暂无工作流</div>
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
            <div class="workflow-card__actions">
              <WorkflowStatusBadge :status="workflow.status" />
              <button type="button" class="workflow-card__copy" @click.stop="copyWorkflowId(workflow.id)">复制ID</button>
            </div>
          </div>
          <p>{{ workflow.progress_summary || '暂无进度摘要' }}</p>
          <div class="workflow-card__meta">
            <span>{{ workflowNeedsConfirmation(workflow) ? '需要确认' : '无需确认' }}</span>
            <span v-if="workflowStepCount(workflow) > 0">子代理/步骤 {{ workflowStepCount(workflow) }}</span>
            <span v-if="workflow.tool_call_count">工具 {{ workflow.tool_call_count }}</span>
            <span v-if="workflow.failure_count">失败 {{ workflow.failure_count }}</span>
            <span v-if="workflow.artifact_count">产物 {{ workflow.artifact_count }}</span>
            <span v-if="workflow.reference_count">引用 {{ workflow.reference_count }}</span>
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
import type {
  MultiAgentSummarySource,
  WorkflowGovernanceSummary,
  WorkflowListResponse,
  WorkflowSummary,
} from './workflowTypes'

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
const copyMessage = ref('')
const workflows = ref<WorkflowSummary[]>([])
const selectedId = ref<number | null>(null)
const governanceSummary = ref<WorkflowGovernanceSummary | null>(null)

type FilterKey = 'all' | 'failed' | 'needs_confirmation' | 'has_artifacts' | 'has_references'

interface FilterOption {
  key: FilterKey
  label: string
}

const filterOptions: FilterOption[] = [
  { key: 'all', label: '全部' },
  { key: 'failed', label: '失败' },
  { key: 'needs_confirmation', label: '需确认' },
  { key: 'has_artifacts', label: '有产物' },
  { key: 'has_references', label: '有引用' },
]
const activeFilter = ref<FilterKey>('all')

const selectedWorkflow = computed(() => workflows.value.find(item => item.id === selectedId.value) || null)
const totalLabel = computed(() => {
  if (copyMessage.value) return copyMessage.value
  return workflows.value.length ? `${workflows.value.length} 个任务` : '无任务'
})

onMounted(() => {
  void loadGovernanceSummary()
  void loadWorkflows()
})

function selectFilter(key: FilterKey) {
  activeFilter.value = key
  void loadWorkflows()
}

function refreshAll() {
  void loadGovernanceSummary()
  void loadWorkflows()
}

async function loadWorkflows() {
  loading.value = true
  error.value = ''
  try {
    const payload = await apiGet<WorkflowListResponse>(workflowListPath())
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

async function loadGovernanceSummary() {
  try {
    governanceSummary.value = await apiGet<WorkflowGovernanceSummary>('/agent/workflows/governance-summary')
  } catch {
    governanceSummary.value = null
  }
}

function workflowListPath(): string {
  const params = new URLSearchParams()
  params.set('limit', '50')
  if (activeFilter.value === 'failed') params.set('has_failures', 'true')
  if (activeFilter.value === 'needs_confirmation') params.set('status', 'needs_confirmation')
  if (activeFilter.value === 'has_artifacts') params.set('has_artifacts', 'true')
  if (activeFilter.value === 'has_references') params.set('has_references', 'true')
  return `/agent/workflows?${params.toString()}`
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

function workflowStepCount(workflow: WorkflowSummary): number {
  return workflow.step_count ?? multiAgentSummaryCount(workflow)
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

async function copyWorkflowId(id: number) {
  const text = String(id)
  try {
    await navigator.clipboard.writeText(text)
    copyMessage.value = `已复制 ${text}`
    window.setTimeout(() => { copyMessage.value = '' }, 1800)
  } catch {
    copyMessage.value = '复制失败'
  }
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
.workflow-summary {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--ag-space-sm);
  padding: var(--ag-space-md) var(--ag-space-2xl);
  border-bottom: 1px solid var(--ag-border-light);
  background: var(--ag-bg-base);
}
.workflow-summary div {
  min-width: 0;
  padding: var(--ag-space-sm);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-card);
}
.workflow-summary span {
  display: block;
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-xs);
}
.workflow-summary strong {
  display: block;
  margin-top: 2px;
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-lg);
  line-height: var(--ag-line-height-tight);
}
.workflow-filters {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--ag-space-xs);
  padding: var(--ag-space-sm) var(--ag-space-2xl);
  border-bottom: 1px solid var(--ag-border-light);
  background: var(--ag-bg-base);
  overflow-x: auto;
}
.workflow-filters button {
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--ag-border-base);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-text-secondary);
  cursor: pointer;
  font-size: var(--ag-font-size-xs);
  white-space: nowrap;
}
.workflow-filters button.active {
  border-color: var(--ag-primary);
  background: var(--ag-primary-light);
  color: var(--ag-primary-dark);
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
.workflow-card__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--ag-space-xs);
}
.workflow-card__copy {
  height: 22px;
  padding: 0 6px;
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-text-tertiary);
  cursor: pointer;
  font-size: var(--ag-font-size-xs);
}
.workflow-card__copy:hover {
  border-color: var(--ag-primary);
  color: var(--ag-primary);
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
  .workflow-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: var(--ag-space-md);
  }
}
</style>
