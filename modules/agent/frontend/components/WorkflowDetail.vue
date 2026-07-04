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
        <div class="workflow-detail__actions">
          <WorkflowStatusBadge :status="currentWorkflow.status" />
          <button type="button" @click="copyWorkflowId">复制ID</button>
          <button type="button" :disabled="!primaryError" @click="copyPrimaryError">复制错误</button>
        </div>
      </header>
      <p v-if="copyMessage" class="workflow-detail__hint">{{ copyMessage }}</p>

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

      <div class="workflow-detail__section">
        <h4>子代理/步骤</h4>
        <div v-if="multiAgentSummary.length" class="multi-agent-list">
          <article
            v-for="(item, index) in multiAgentSummary"
            :key="multiAgentItemKey(item, index)"
            class="multi-agent-row"
          >
            <div class="multi-agent-row__top">
              <strong>{{ multiAgentTitle(item, index) }}</strong>
              <WorkflowStatusBadge :status="item.status" />
            </div>
            <dl class="multi-agent-fields">
              <div>
                <dt>完成摘要</dt>
                <dd>{{ item.completion_summary || '暂无完成摘要' }}</dd>
              </div>
              <div>
                <dt>失败原因</dt>
                <dd>{{ item.failure_reason || '无失败原因' }}</dd>
              </div>
              <div>
                <dt>引用/产物 ID</dt>
                <dd>
                  <EvidenceReferenceList
                    v-if="multiAgentEvidenceReferences(item).length"
                    :references="multiAgentEvidenceReferences(item)"
                    dense
                  />
                  <template v-else>暂无引用或产物</template>
                </dd>
              </div>
              <div>
                <dt>下一步建议</dt>
                <dd>{{ item.next_action || '暂无下一步建议' }}</dd>
              </div>
            </dl>
          </article>
        </div>
        <p v-else class="workflow-muted">还没有子代理或步骤摘要；任务开始分派后会在这里显示。</p>
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
                  <div v-if="stepEvidenceReferences(step).length" class="ledger-row__refs">
                    <EvidenceReferenceList :references="stepEvidenceReferences(step)" dense />
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
                  <div v-if="toolCallEvidenceReferences(toolCall).length" class="ledger-row__refs">
                    <EvidenceReferenceList :references="toolCallEvidenceReferences(toolCall)" dense />
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
                  <div v-if="verificationEvidenceReferences(verification).length" class="ledger-row__refs">
                    <EvidenceReferenceList :references="verificationEvidenceReferences(verification)" dense />
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
                  <div v-if="failureEvidenceReferences(failure).length" class="ledger-row__refs">
                    <EvidenceReferenceList :references="failureEvidenceReferences(failure)" dense />
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
                  <div v-if="artifactEvidenceReferences(artifact).length" class="ledger-row__refs">
                    <EvidenceReferenceList :references="artifactEvidenceReferences(artifact)" dense />
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
import EvidenceReferenceList from './EvidenceReferenceList.vue'
import WorkflowStatusBadge from './WorkflowStatusBadge.vue'
import {
  collectEvidenceReferences,
  evidenceReferencesFromIds,
  type EvidenceReference,
} from './evidenceReferences'
import type {
  JsonValue,
  MultiAgentSummaryItem,
  MultiAgentSummaryResponse,
  MultiAgentSummarySource,
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
const multiAgentSummary = ref<MultiAgentSummaryItem[]>([])
let requestToken = 0

const currentWorkflow = computed<WorkflowDetailPayload | WorkflowSummary | null>(() => detail.value || props.summary || null)
const workflowNeedsConfirmation = computed(() => {
  const current = currentWorkflow.value
  return Boolean(current?.needs_confirmation || current?.status === 'needs_confirmation')
})
const artifactSummaryItems = computed(() => formatArtifactSummary(currentWorkflow.value?.artifact_summary))
const queueTaskSummary = computed(() => formatJsonSummary(currentWorkflow.value?.queue_task_ids))
const copyMessage = ref('')
const primaryError = computed(() => {
  for (const item of multiAgentSummary.value) {
    if (item.failure_reason) return item.failure_reason
  }
  for (const item of failures.value) {
    if (item.handoff_note || item.error_signature) return item.handoff_note || item.error_signature || ''
  }
  for (const item of verifications.value) {
    if (item.status === 'fail' && item.summary) return item.summary
  }
  const summary = currentWorkflow.value?.progress_summary
  return currentWorkflow.value?.status === 'failed' && summary ? summary : ''
})

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
  multiAgentSummary.value = normalizeMultiAgentSummary(props.summary?.multi_agent_summary)
  if (!runId) return
  loading.value = true
  try {
    const payload = await apiGet<WorkflowDetailPayload>(`/agent/workflows/${runId}`)
    if (token === requestToken) {
      detail.value = payload
      multiAgentSummary.value = normalizeMultiAgentSummary(payload.multi_agent_summary)
      if (multiAgentSummary.value.length === 0) {
        const optionalSummary = await fetchOptionalMultiAgentSummary(runId)
        if (token === requestToken) multiAgentSummary.value = optionalSummary
      }
    }
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

async function fetchOptionalMultiAgentSummary(runId: number): Promise<MultiAgentSummaryItem[]> {
  try {
    const payload = await apiGet<MultiAgentSummaryResponse>(`/agent/workflows/${runId}/multi-agent-summary`)
    return normalizeMultiAgentSummary(payload)
  } catch {
    return []
  }
}

function normalizeMultiAgentSummary(source: MultiAgentSummarySource | undefined): MultiAgentSummaryItem[] {
  if (!source) return []
  return Array.isArray(source) ? source : source.items ?? []
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

function multiAgentItemKey(item: MultiAgentSummaryItem, index: number): string {
  const stableId = item.id ?? item.agent_id ?? item.step_id
  return stableId === undefined || stableId === null ? `multi-agent-${index}` : `multi-agent-${String(stableId)}-${index}`
}

function multiAgentTitle(item: MultiAgentSummaryItem, index: number): string {
  return item.title || item.agent_name || item.name || item.step_key || `步骤 #${index + 1}`
}

function multiAgentEvidenceReferences(item: MultiAgentSummaryItem): EvidenceReference[] {
  return [
    ...collectEvidenceReferences(item.reference_ids, {
      sourceTool: item.step_key || item.agent_name || item.name || item.title,
      status: item.status,
    }),
    ...evidenceReferencesFromIds('artifact_id', item.artifact_ids, {
      sourceTool: item.step_key || item.agent_name || item.name || item.title,
      status: item.status,
    }),
  ]
}

function stepEvidenceReferences(step: WorkflowStep): EvidenceReference[] {
  const sourceTool = step.step_key || step.title || `step:${step.id}`
  return [
    ...collectEvidenceReferences(step.input_ref, { sourceTool, status: step.status }),
    ...collectEvidenceReferences(step.output_ref, { sourceTool, status: step.status }),
  ]
}

function toolCallEvidenceReferences(toolCall: WorkflowToolCall): EvidenceReference[] {
  return collectEvidenceReferences(toolCall.result_ref, {
    sourceTool: toolCall.tool_name,
    status: toolCall.status,
  })
}

function artifactEvidenceReferences(artifact: WorkflowArtifact): EvidenceReference[] {
  return collectEvidenceReferences(artifact.storage_ref, {
    sourceTool: artifact.artifact_type || artifact.storage_kind,
    status: artifact.lifecycle,
  })
}

function verificationEvidenceReferences(verification: WorkflowVerification): EvidenceReference[] {
  return collectEvidenceReferences(verification.evidence_ref, {
    sourceTool: verification.verification_type,
    status: verification.status,
  })
}

function failureEvidenceReferences(failure: WorkflowFailure): EvidenceReference[] {
  return collectEvidenceReferences(failure.evidence_ref, {
    sourceTool: failure.failure_type,
    status: failure.next_action,
  })
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

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copyMessage.value = `已复制 ${text.length > 36 ? `${text.slice(0, 34)}...` : text}`
    window.setTimeout(() => { copyMessage.value = '' }, 1800)
  } catch {
    copyMessage.value = '复制失败'
  }
}

function copyWorkflowId() {
  const id = currentWorkflow.value?.id
  if (id !== undefined) void copyText(String(id))
}

function copyPrimaryError() {
  if (primaryError.value) void copyText(primaryError.value)
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
.workflow-detail__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--ag-space-xs);
}
.workflow-detail__actions button {
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--ag-border-base);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-text-secondary);
  cursor: pointer;
  font-size: var(--ag-font-size-xs);
}
.workflow-detail__actions button:hover:not(:disabled) {
  border-color: var(--ag-primary);
  color: var(--ag-primary);
}
.workflow-detail__actions button:disabled {
  opacity: 0.55;
  cursor: default;
}
.workflow-detail__hint {
  margin: calc(var(--ag-space-sm) * -1) 0 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-xs);
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
.multi-agent-list {
  display: flex;
  flex-direction: column;
  gap: var(--ag-space-sm);
}
.multi-agent-row {
  min-width: 0;
  padding: var(--ag-space-md);
  background: var(--ag-bg-card);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-md);
}
.multi-agent-row__top {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ag-space-sm);
  margin-bottom: var(--ag-space-sm);
}
.multi-agent-row__top strong {
  min-width: 0;
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-base);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.multi-agent-fields {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--ag-space-sm) var(--ag-space-md);
}
.multi-agent-fields div {
  min-width: 0;
}
.multi-agent-fields dt {
  margin-bottom: 2px;
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-xs);
}
.multi-agent-fields dd {
  min-width: 0;
  margin: 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-sm);
  line-height: var(--ag-line-height-base);
  word-break: break-word;
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
  flex-wrap: wrap;
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
.ledger-row__refs {
  flex-basis: 100%;
  min-width: 0;
}
.workflow-muted {
  margin: 0;
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-base);
}
@media (max-width: 900px) {
  .workflow-detail__summary-grid { grid-template-columns: 1fr; }
  .multi-agent-row__top { align-items: flex-start; }
  .multi-agent-fields { grid-template-columns: 1fr; }
  .ledger-row { flex-direction: column; }
  .ledger-row__meta { max-width: none; justify-content: flex-start; }
}
</style>
