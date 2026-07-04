<template>
  <section class="workflow-detail">
    <div v-if="loading" class="workflow-detail__state">加载中...</div>
    <div v-else-if="loadError" class="workflow-detail__state workflow-detail__state--error">{{ loadError }}</div>
    <template v-else-if="currentWorkflow">
      <header class="workflow-detail__header">
        <div class="workflow-detail__title-block">
          <h3>{{ currentWorkflow.title }}</h3>
          <p>{{ currentWorkflow.progress_summary || '暂无进度摘要' }}</p>
        </div>
        <WorkflowStatusBadge :status="currentWorkflow.status" />
      </header>

      <div class="workflow-detail__summary-grid">
        <div>
          <span class="summary-label">验证</span>
          <strong>{{ verificationLabel(currentWorkflow.verification_status) }}</strong>
        </div>
        <div>
          <span class="summary-label">确认</span>
          <strong>{{ workflowNeedsConfirmation ? '需要确认' : '无需确认' }}</strong>
        </div>
        <div>
          <span class="summary-label">更新时间</span>
          <strong>{{ formatDateTime(currentWorkflow.updated_at) }}</strong>
        </div>
      </div>

      <div class="workflow-detail__section">
        <h4>产物摘要</h4>
        <div v-if="artifactSummaryItems.length" class="artifact-summary">
          <span v-for="item in artifactSummaryItems" :key="item" class="artifact-chip">{{ item }}</span>
        </div>
        <p v-else class="workflow-muted">暂无产物</p>
      </div>

      <div v-if="workflowNeedsConfirmation" class="confirmation-strip">
        <span>该任务正等待确认</span>
        <button v-if="isAdmin" type="button" @click="$emit('openApprovals')">打开审批</button>
      </div>

      <div v-if="isAdmin" class="workflow-detail__admin">
        <button type="button" class="ledger-toggle" @click="toggleLedger">
          {{ ledgerOpen ? '收起账本' : '展开账本' }}
        </button>

        <div v-if="ledgerOpen" class="ledger">
          <div v-if="ledgerLoading" class="workflow-detail__state">加载账本...</div>
          <div v-else>
            <section v-if="currentWorkflow.developer_summary" class="ledger-section">
              <h4>开发摘要</h4>
              <p>{{ currentWorkflow.developer_summary }}</p>
            </section>

            <section class="ledger-section">
              <h4>步骤</h4>
              <div v-if="steps.length" class="ledger-list">
                <article v-for="step in steps" :key="step.id" class="ledger-row">
                  <div class="ledger-row__main">
                    <strong>{{ step.title || step.step_key || `步骤 #${step.id}` }}</strong>
                    <span>{{ step.summary || '-' }}</span>
                  </div>
                  <div class="ledger-row__meta">
                    <WorkflowStatusBadge :status="step.status" />
                    <span>{{ step.type || '-' }}</span>
                    <span v-if="step.error_signature">{{ step.error_signature }}</span>
                  </div>
                </article>
              </div>
              <p v-else class="workflow-muted">暂无步骤记录</p>
            </section>

            <section class="ledger-section">
              <h4>工具调用</h4>
              <div v-if="toolCalls.length" class="ledger-list">
                <article v-for="toolCall in toolCalls" :key="toolCall.id" class="ledger-row">
                  <div class="ledger-row__main">
                    <strong>{{ toolCall.tool_name }}</strong>
                    <span>{{ toolTarget(toolCall) }}</span>
                  </div>
                  <div class="ledger-row__meta">
                    <WorkflowStatusBadge :status="toolCall.status" />
                    <span>{{ toolCall.side_effect_level || '-' }}</span>
                    <span>{{ toolCall.approval_policy || '-' }}</span>
                    <span v-if="toolCall.arguments_hash">args: {{ shortHash(toolCall.arguments_hash) }}</span>
                    <span v-if="toolCall.idempotency_key">idem: {{ shortHash(toolCall.idempotency_key) }}</span>
                  </div>
                </article>
              </div>
              <p v-else class="workflow-muted">暂无工具调用</p>
            </section>

            <section class="ledger-section">
              <h4>验证</h4>
              <div v-if="verifications.length" class="ledger-list">
                <article v-for="verification in verifications" :key="verification.id" class="ledger-row">
                  <div class="ledger-row__main">
                    <strong>{{ verification.verification_type }}</strong>
                    <span>{{ verification.summary || verification.command_or_capability || '-' }}</span>
                  </div>
                  <div class="ledger-row__meta">
                    <WorkflowStatusBadge :status="verification.status" />
                    <span>{{ verification.is_required_for_completion ? 'required' : 'optional' }}</span>
                    <span v-if="verification.duration_ms">{{ verification.duration_ms }}ms</span>
                  </div>
                </article>
              </div>
              <p v-else class="workflow-muted">暂无验证记录</p>
            </section>

            <section class="ledger-section">
              <h4>失败记录</h4>
              <div v-if="failures.length" class="ledger-list">
                <article v-for="failure in failures" :key="failure.id" class="ledger-row">
                  <div class="ledger-row__main">
                    <strong>{{ failure.failure_type }}</strong>
                    <span>{{ failure.handoff_note || failure.error_signature || '-' }}</span>
                  </div>
                  <div class="ledger-row__meta">
                    <span>{{ failure.next_action || '-' }}</span>
                    <span>{{ failure.retryable ? 'retryable' : 'not retryable' }}</span>
                  </div>
                </article>
              </div>
              <p v-else class="workflow-muted">暂无失败记录</p>
            </section>

            <section class="ledger-section">
              <h4>产物</h4>
              <div v-if="artifacts.length" class="ledger-list">
                <article v-for="artifact in artifacts" :key="artifact.id" class="ledger-row">
                  <div class="ledger-row__main">
                    <strong>{{ artifact.artifact_type }}</strong>
                    <span>{{ artifact.summary || artifact.storage_kind || '-' }}</span>
                  </div>
                  <div class="ledger-row__meta">
                    <span>{{ artifact.lifecycle || '-' }}</span>
                    <span>{{ artifact.visibility || '-' }}</span>
                    <span v-if="artifact.storage_ref">{{ compactValue(artifact.storage_ref) }}</span>
                  </div>
                </article>
              </div>
              <p v-else class="workflow-muted">暂无产物记录</p>
            </section>

            <section v-if="queueTaskSummary" class="ledger-section">
              <h4>队列任务</h4>
              <p>{{ queueTaskSummary }}</p>
            </section>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="workflow-detail__state">选择一个工作流</div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiGet } from '../api'
import WorkflowStatusBadge from './WorkflowStatusBadge.vue'
import type {
  JsonValue,
  WorkflowArtifact,
  WorkflowDetailPayload,
  WorkflowFailure,
  WorkflowStep,
  WorkflowSummary,
  WorkflowToolCall,
  WorkflowVerification,
} from './workflowTypes'

const props = withDefaults(defineProps<{
  runId: number | null
  summary?: WorkflowSummary | null
  isAdmin?: boolean
}>(), {
  summary: null,
  isAdmin: false,
})

defineEmits<{
  openApprovals: []
}>()

const loading = ref(false)
const ledgerLoading = ref(false)
const ledgerOpen = ref(false)
const loadError = ref('')
const detail = ref<WorkflowDetailPayload | null>(null)
const steps = ref<WorkflowStep[]>([])
const toolCalls = ref<WorkflowToolCall[]>([])
const artifacts = ref<WorkflowArtifact[]>([])
const verifications = ref<WorkflowVerification[]>([])
const failures = ref<WorkflowFailure[]>([])
let requestToken = 0

const currentWorkflow = computed<WorkflowDetailPayload | WorkflowSummary | null>(() => detail.value || props.summary || null)
const workflowNeedsConfirmation = computed(() => {
  const current = currentWorkflow.value
  return Boolean(current?.needs_confirmation || current?.status === 'needs_confirmation')
})
const artifactSummaryItems = computed(() => formatArtifactSummary(currentWorkflow.value?.artifact_summary))
const queueTaskSummary = computed(() => formatJsonSummary(currentWorkflow.value?.queue_task_ids))

watch(() => props.runId, () => {
  ledgerOpen.value = false
  void loadDetail()
}, { immediate: true })

async function loadDetail() {
  const runId = props.runId
  const token = ++requestToken
  loadError.value = ''
  detail.value = props.summary ? { ...props.summary } : null
  steps.value = []
  toolCalls.value = []
  artifacts.value = []
  verifications.value = []
  failures.value = []
  if (!runId) return
  loading.value = true
  try {
    const payload = await apiGet<WorkflowDetailPayload>(`/agent/workflows/${runId}`)
    if (token === requestToken) detail.value = payload
  } catch (error: unknown) {
    if (token === requestToken) loadError.value = readableError(error)
  } finally {
    if (token === requestToken) loading.value = false
  }
}

async function toggleLedger() {
  ledgerOpen.value = !ledgerOpen.value
  if (ledgerOpen.value && props.runId) {
    await loadLedger(props.runId)
  }
}

async function loadLedger(runId: number) {
  ledgerLoading.value = true
  const detailValue = detail.value
  try {
    const [stepRows, toolRows, artifactRows, verificationRows, failureRows] = await Promise.all([
      fetchOptionalList<WorkflowStep>(`/agent/workflows/${runId}/steps`, detailValue?.steps),
      fetchOptionalList<WorkflowToolCall>(`/agent/workflows/${runId}/tool-calls`, detailValue?.tool_calls),
      fetchOptionalList<WorkflowArtifact>(`/agent/workflows/${runId}/artifacts`, detailValue?.artifacts),
      fetchOptionalList<WorkflowVerification>(`/agent/workflows/${runId}/verifications`, detailValue?.verifications),
      fetchOptionalList<WorkflowFailure>(`/agent/workflows/${runId}/failures`, detailValue?.failures),
    ])
    steps.value = stepRows
    toolCalls.value = toolRows
    artifacts.value = artifactRows
    verifications.value = verificationRows
    failures.value = failureRows
  } finally {
    ledgerLoading.value = false
  }
}

interface ListPayload<T> {
  items?: T[]
}

async function fetchOptionalList<T>(path: string, fallback?: T[]): Promise<T[]> {
  if (fallback?.length) return fallback
  try {
    const payload = await apiGet<T[] | ListPayload<T>>(path)
    return Array.isArray(payload) ? payload : payload.items ?? []
  } catch {
    return []
  }
}

function verificationLabel(status: string | null | undefined): string {
  const labels: Record<string, string> = {
    pending: '待验证',
    pass: '通过',
    fail: '失败',
    debt: '有债务',
    skipped: '已跳过',
  }
  return labels[status || 'pending'] || status || '待验证'
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatArtifactSummary(value: JsonValue | undefined): string[] {
  if (value === undefined || value === null) return []
  if (typeof value === 'string') return value ? [value] : []
  if (typeof value === 'number' || typeof value === 'boolean') return [String(value)]
  if (Array.isArray(value)) return value.length ? [`${value.length} 项产物`] : []
  if (!isRecord(value)) return []
  return Object.entries(value)
    .slice(0, 6)
    .map(([key, item]) => `${key}: ${compactValue(item)}`)
}

function compactValue(value: unknown): string {
  if (value === null) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return `${value.length} 项`
  if (!isRecord(value)) return '-'
  return `${Object.keys(value).length} 项`
}

function formatJsonSummary(value: JsonValue | undefined): string {
  if (value === undefined || value === null) return ''
  if (Array.isArray(value)) return value.length ? `${value.length} 个队列任务` : ''
  if (isRecord(value)) return `${Object.keys(value).length} 个队列字段`
  return String(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function shortHash(value: string): string {
  return value.length > 14 ? `${value.slice(0, 10)}...` : value
}

function toolTarget(toolCall: WorkflowToolCall): string {
  const parts = [toolCall.target_module, toolCall.action].filter((item): item is string => Boolean(item))
  return parts.length ? parts.join(':') : toolCall.caller || '-'
}

function readableError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  if (message.includes('404') || message.includes('Unexpected token')) {
    return '工作流接口暂未可用'
  }
  return message || '加载失败'
}
</script>

<style scoped>
.workflow-detail {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-lg);
}
.workflow-detail__state {
  padding: var(--ag-space-3xl);
  color: var(--ag-text-tertiary);
  text-align: center;
}
.workflow-detail__state--error { color: var(--ag-error); }
.workflow-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ag-space-lg);
}
.workflow-detail__title-block { min-width: 0; }
.workflow-detail__title-block h3 {
  margin: 0;
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-xl);
  line-height: var(--ag-line-height-tight);
}
.workflow-detail__title-block p {
  margin: var(--ag-space-xs) 0 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-base);
  line-height: var(--ag-line-height-base);
}
.workflow-detail__summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--ag-space-sm);
}
.workflow-detail__summary-grid > div {
  min-width: 0;
  padding: var(--ag-space-md);
  background: var(--ag-bg-card);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-md);
}
.summary-label {
  display: block;
  margin-bottom: var(--ag-space-xs);
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-xs);
}
.workflow-detail__summary-grid strong {
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-base);
  font-weight: 600;
  word-break: break-word;
}
.workflow-detail__section h4,
.ledger-section h4 {
  margin: 0 0 var(--ag-space-sm);
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-base);
}
.artifact-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ag-space-sm);
}
.artifact-chip {
  max-width: 100%;
  padding: 4px 8px;
  background: var(--ag-bg-active);
  border: 1px solid #c8e6ef;
  border-radius: var(--ag-radius-sm);
  color: var(--ag-primary-dark);
  font-size: var(--ag-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.confirmation-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ag-space-md);
  padding: var(--ag-space-md);
  border: 1px solid #f2d58a;
  border-radius: var(--ag-radius-md);
  background: #fff8e6;
  color: #7a5400;
  font-size: var(--ag-font-size-base);
}
.confirmation-strip button,
.ledger-toggle {
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--ag-border-base);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-text-secondary);
  cursor: pointer;
  font-size: var(--ag-font-size-sm);
}
.confirmation-strip button:hover,
.ledger-toggle:hover {
  border-color: var(--ag-primary);
  color: var(--ag-primary);
}
.workflow-detail__admin {
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-md);
}
.ledger {
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-lg);
  padding-top: var(--ag-space-sm);
  border-top: 1px solid var(--ag-border-light);
}
.ledger-section {
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-sm);
}
.ledger-section p {
  margin: 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-base);
  line-height: var(--ag-line-height-base);
}
.ledger-list {
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-sm);
}
.ledger-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ag-space-md);
  padding: var(--ag-space-md);
  background: var(--ag-bg-card);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-md);
}
.ledger-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ledger-row__main strong {
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-base);
}
.ledger-row__main span,
.ledger-row__meta span {
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-xs);
  line-height: var(--ag-line-height-base);
  word-break: break-word;
}
.ledger-row__meta {
  flex-shrink: 0;
  max-width: 48%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--ag-space-xs);
}
.workflow-muted {
  margin: 0;
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-base);
}
@media (max-width: 900px) {
  .workflow-detail__summary-grid { grid-template-columns: 1fr; }
  .ledger-row { flex-direction: column; }
  .ledger-row__meta { max-width: none; justify-content: flex-start; }
}
</style>
