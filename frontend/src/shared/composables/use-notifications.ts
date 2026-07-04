import { computed, ref, onMounted, onUnmounted, type Ref } from 'vue'
import api from '@/shared/api'
import type { NotificationItem } from '@/shared/api/types'
import { displayApiError } from '@/shared/api/response-transform'
import { createLoadState, failLoading, finishLoading, startLoading, type LoadState } from '@/shared/composables/use-load-state'

export interface TaskAuditSummary {
  pending: number
  running: number
  completed: number
  failed: number
}

export interface TaskAuditClassification {
  recent_failed_count: number
  historical_failed_debt_count: number
  actionable_pending_count: number
  stale_pending_debt_count: number
  future_scheduled_count: number
  healthy_running_count: number
  orphan_running_debt_count: number
  completed_semantic_failure_count: number
  completed_semantic_failure_manual_review_count: number
}

export interface TaskDebtSummary {
  summary: TaskAuditSummary
  classification: TaskAuditClassification
  recent_failed_count: number
  historical_debt_total: number
}

export interface AgentWorkflowItem {
  id: number
  title?: string | null
  status: string
  updated_at?: string | null
  needs_confirmation?: boolean
  terminal_status?: string | null
  verification_status?: string | null
  progress_summary?: string | null
}

export interface AgentWorkflowSummary {
  items: AgentWorkflowItem[]
  total: number
  active_count: number
  needs_confirmation_count: number
  failed_count: number
  partial_count: number
}

interface AgentWorkflowListResponse {
  items: AgentWorkflowItem[]
  total: number
}

export type ActionItemSourceType = 'notification' | 'model_fallback' | 'task' | 'agent_workflow' | 'knowledge_document' | 'knowledge_governance'
export type ActionItemSeverity = 'info' | 'warning' | 'error' | 'success'

export interface ActionTarget {
  app_key: string
  payload?: Record<string, unknown>
}

export interface ActionItemSecondaryAction {
  id: string
  label: string
  kind: 'retry' | 'ignore' | 'archive' | 'details'
}

export interface ActionItem {
  id: string
  source_type: ActionItemSourceType
  source_id: string
  title: string
  description: string
  severity: ActionItemSeverity
  visible_status: string
  action_label?: string
  action_target?: ActionTarget
  action_payload?: Record<string, unknown>
  secondary_actions: ActionItemSecondaryAction[]
  can_retry: boolean
  can_archive: boolean
  created_at?: string | null
  updated_at?: string | null
}

interface ModelFallbackNotice {
  primaryModel: string
  fallbackModel: string
  primaryFailed: boolean
  fallbackUsed: boolean
  finalSuccess: boolean
  failureCategory: string
  failureCode?: string
  reason: string
}

interface KnowledgeDashboardStats {
  failed_documents: number
  source_unavailable_documents?: number
  stuck_documents: Array<{
    id: number
    filename: string
    source_available?: boolean
    source_state?: string
    raw_status?: string
    fusion_status?: string
    parse_status?: string
  }>
}

interface KnowledgePendingCount {
  pending_count: number
}

export type NotificationLoadSource =
  | 'unreadCount'
  | 'notifications'
  | 'taskDebt'
  | 'agentWorkflows'
  | 'knowledgeStats'
  | 'knowledgeGovernance'

export interface NotificationLoadIssue {
  source: NotificationLoadSource
  label: string
  status: 'error' | 'stale'
  message: string
  backendMessage?: string
  copyText: string
  sourceTarget?: ActionTarget
}

export function useNotifications(containerSelector = '.taskbar-notifications-wrapper') {
  const unreadCount = ref(0)
  const notificationList = ref<NotificationItem[]>([])
  const taskDebtSummary = ref<TaskDebtSummary | null>(null)
  const agentWorkflowSummary = ref<AgentWorkflowSummary | null>(null)
  const knowledgeStats = ref<KnowledgeDashboardStats | null>(null)
  const knowledgePendingCount = ref(0)
  const dismissedActionItemIds = ref<Set<string>>(new Set())
  const showNotificationPanel = ref(false)

  const unreadCountLoadState = createLoadState(0)
  const notificationListLoadState = createLoadState<NotificationItem[]>([])
  const taskDebtLoadState = createLoadState<TaskDebtSummary | null>(null)
  const agentWorkflowLoadState = createLoadState<AgentWorkflowSummary | null>(null)
  const knowledgeStatsLoadState = createLoadState<KnowledgeDashboardStats | null>(null)
  const knowledgePendingLoadState = createLoadState(0)

  const loadStateLabels: Record<NotificationLoadSource, string> = {
    unreadCount: '未读通知',
    notifications: '通知列表',
    taskDebt: '后台任务',
    agentWorkflows: 'Agent 工作',
    knowledgeStats: '知识库状态',
    knowledgeGovernance: '知识治理',
  }

  const feedbackLoadIssues = computed<NotificationLoadIssue[]>(() => [
    issueFromState('unreadCount', unreadCountLoadState.value),
    issueFromState('notifications', notificationListLoadState.value),
    issueFromState('taskDebt', taskDebtLoadState.value),
    issueFromState('agentWorkflows', agentWorkflowLoadState.value),
    issueFromState('knowledgeStats', knowledgeStatsLoadState.value),
    issueFromState('knowledgeGovernance', knowledgePendingLoadState.value),
  ].filter((issue): issue is NotificationLoadIssue => issue !== null))
  const hasFeedbackLoadError = computed(() => feedbackLoadIssues.value.some((issue) => issue.status === 'error'))
  const hasStaleFeedbackData = computed(() => feedbackLoadIssues.value.some((issue) => issue.status === 'stale'))
  const isFeedbackLoading = computed(() => [
    unreadCountLoadState.value,
    notificationListLoadState.value,
    taskDebtLoadState.value,
    agentWorkflowLoadState.value,
    knowledgeStatsLoadState.value,
    knowledgePendingLoadState.value,
  ].some((state) => state.status === 'loading'))

  const taskSignalCount = computed(() => {
    const summary = taskDebtSummary.value
    if (!summary) return 0
    return summary.summary.pending
      + summary.summary.running
      + summary.recent_failed_count
      + summary.historical_debt_total
      + summary.classification.stale_pending_debt_count
      + summary.classification.orphan_running_debt_count
      + summary.classification.completed_semantic_failure_count
  })

  const agentSignalCount = computed(() => {
    const summary = agentWorkflowSummary.value
    if (!summary) return 0
    return summary.active_count
      + summary.needs_confirmation_count
      + summary.failed_count
      + summary.partial_count
  })
  const knowledgeSignalCount = computed(() => {
    const stats = knowledgeStats.value
    const failedLive = stats?.stuck_documents.filter((doc) => doc.source_available !== false).length ?? 0
    return (stats?.source_unavailable_documents ?? 0) + failedLive + knowledgePendingCount.value
  })

  const feedbackSignalCount = computed(() => (
    unreadCount.value + taskSignalCount.value + agentSignalCount.value + knowledgeSignalCount.value
  ))
  const actionItems = computed<ActionItem[]>(() => {
    const items: ActionItem[] = []

    for (const notification of notificationList.value.filter((item) => !item.is_read).slice(0, 5)) {
      const modelFallback = modelFallbackFromNotification(notification)
      if (modelFallback) {
        items.push({
          id: `model_fallback:${notification.id}`,
          source_type: 'model_fallback',
          source_id: String(notification.id),
          title: modelFallback.finalSuccess ? '模型已降级但任务继续完成' : '模型降级失败需要处理',
          description: modelFallbackDescription(modelFallback),
          severity: modelFallback.finalSuccess ? 'warning' : 'error',
          visible_status: modelFallback.finalSuccess ? '已降级' : '失败',
          secondary_actions: [{ id: 'archive', label: '本次忽略', kind: 'archive' }],
          can_retry: !modelFallback.finalSuccess,
          can_archive: true,
          created_at: notification.published_at,
          updated_at: notification.published_at,
        })
        continue
      }
      items.push({
        id: `notification:${notification.id}`,
        source_type: 'notification',
        source_id: String(notification.id),
        title: notification.title,
        description: '这条通知还没有处理。',
        severity: notificationSeverity(notification.notification_type),
        visible_status: '需要确认',
        action_label: '标为已读',
        secondary_actions: [{ id: 'archive', label: '忽略', kind: 'archive' }],
        can_retry: false,
        can_archive: true,
        created_at: notification.published_at,
        updated_at: notification.published_at,
      })
    }

    const taskSummary = taskDebtSummary.value
    if (taskSummary) {
      const problemCount = taskProblemCount(taskSummary)
      if (problemCount > 0) {
        items.push({
          id: 'task:worker-audit',
          source_type: 'task',
          source_id: 'worker-audit',
          title: '后台任务需要查看',
          description: `失败 ${taskSummary.summary.failed}，近期失败 ${taskSummary.classification.recent_failed_count}，历史债务 ${taskSummary.historical_debt_total}。`,
          severity: 'warning',
          visible_status: '部分完成',
          secondary_actions: [{ id: 'archive', label: '本次忽略', kind: 'ignore' }],
          can_retry: false,
          can_archive: true,
        })
      } else if (taskSummary.summary.pending + taskSummary.summary.running > 0) {
        items.push({
          id: 'task:worker-active',
          source_type: 'task',
          source_id: 'worker-active',
          title: '后台任务处理中',
          description: `等待中 ${taskSummary.summary.pending}，处理中 ${taskSummary.summary.running}。`,
          severity: 'info',
          visible_status: taskSummary.summary.running > 0 ? '处理中' : '等待中',
          secondary_actions: [{ id: 'archive', label: '本次忽略', kind: 'ignore' }],
          can_retry: false,
          can_archive: true,
        })
      }
    }

    const workflowSummary = agentWorkflowSummary.value
    if (workflowSummary) {
      for (const workflow of workflowSummary.items.slice(0, 5)) {
        const visibleStatus = userStatusLabel(workflow.status)
        if (visibleStatus === '已完成' || visibleStatus === '已取消') continue
        const workflowPayload: Record<string, unknown> = {
          workflowId: workflow.id,
          status: workflow.status,
        }
        if (workflow.progress_summary) workflowPayload.progressSummary = workflow.progress_summary
        items.push({
          id: `agent_workflow:${workflow.id}`,
          source_type: 'agent_workflow',
          source_id: String(workflow.id),
          title: workflow.title || `Agent 工作 #${workflow.id}`,
          description: workflow.progress_summary || workflowDescription(visibleStatus),
          severity: visibleStatus === '失败' ? 'error' : visibleStatus === '需要确认' ? 'warning' : 'info',
          visible_status: visibleStatus,
          action_label: '打开 Agent',
          action_target: { app_key: 'agent', payload: { workflow: workflowPayload } },
          action_payload: workflowPayload,
          secondary_actions: [{ id: 'archive', label: '本次忽略', kind: 'ignore' }],
          can_retry: ['失败', '部分完成'].includes(visibleStatus),
          can_archive: true,
          updated_at: workflow.updated_at,
        })
      }
    }

    const stats = knowledgeStats.value
    if (stats) {
      const unavailable = stats.source_unavailable_documents ?? 0
      if (unavailable > 0) {
        const firstUnavailable = stats.stuck_documents.find((doc) => doc.source_available === false)
        const payload = firstUnavailable ? { documentId: firstUnavailable.id, sourceState: firstUnavailable.source_state } : { view: 'dashboard' }
        items.push({
          id: 'knowledge_document:source-unavailable',
          source_type: 'knowledge_document',
          source_id: firstUnavailable ? String(firstUnavailable.id) : 'source-unavailable',
          title: `${unavailable} 份知识库资料源文件不可用`,
          description: firstUnavailable
            ? `先处理「${firstUnavailable.filename}」：恢复源文件、重新上传，或确认后删除无效记录。`
            : '请到知识库看板查看源文件不可用的资料。',
          severity: 'warning',
          visible_status: '需要确认',
          action_label: '打开知识库',
          action_target: { app_key: 'knowledge', payload },
          action_payload: payload,
          secondary_actions: [{ id: 'archive', label: '本次忽略', kind: 'ignore' }],
          can_retry: false,
          can_archive: true,
        })
      }

      const failedLive = stats.stuck_documents.filter((doc) => doc.source_available !== false).length
      if (failedLive > 0) {
        const firstFailed = stats.stuck_documents.find((doc) => doc.source_available !== false)
        const payload = firstFailed ? { documentId: firstFailed.id } : { view: 'dashboard' }
        items.push({
          id: 'knowledge_document:failed-live',
          source_type: 'knowledge_document',
          source_id: firstFailed ? String(firstFailed.id) : 'failed-live',
          title: `${failedLive} 份知识库资料分析失败`,
          description: firstFailed ? `可从「${firstFailed.filename}」开始重新分析。` : '请到知识库看板重新触发分析。',
          severity: 'error',
          visible_status: '失败',
          action_label: '打开知识库',
          action_target: { app_key: 'knowledge', payload },
          action_payload: payload,
          secondary_actions: [
            { id: 'retry', label: '去重试', kind: 'retry' },
            { id: 'archive', label: '本次忽略', kind: 'ignore' },
          ],
          can_retry: true,
          can_archive: true,
        })
      }
    }

    if (knowledgePendingCount.value > 0) {
      items.push({
        id: 'knowledge_governance:pending',
        source_type: 'knowledge_governance',
        source_id: 'pending',
        title: `${knowledgePendingCount.value} 个知识治理待办`,
        description: '有实体候选、消歧或校准事项等待处理。',
        severity: 'info',
        visible_status: '需要确认',
        action_label: '打开治理',
        action_target: { app_key: 'knowledge', payload: { view: 'dashboard', showGovernance: true } },
        action_payload: { view: 'dashboard', showGovernance: true },
        secondary_actions: [{ id: 'archive', label: '本次忽略', kind: 'ignore' }],
        can_retry: false,
        can_archive: true,
      })
    }

    return items.filter((item) => !dismissedActionItemIds.value.has(item.id))
  })

  async function loadUnreadCount() {
    await loadWithState(unreadCountLoadState, async () => {
      const data = await api.get<unknown, { unread_count: number }>('/notifications/unread-count')
      return data.unread_count
    }, (count) => { unreadCount.value = count }, '未读通知加载失败')
  }

  async function loadNotificationList() {
    await loadWithState(notificationListLoadState, async () => {
      const data = await api.get<unknown, { list: NotificationItem[] }>('/notifications')
      return data.list
    }, (items) => { notificationList.value = items }, '通知列表加载失败')
  }

  async function loadTaskDebtSummary() {
    await loadWithState(taskDebtLoadState, async () => (
      await api.get<unknown, TaskDebtSummary>('/tasks/worker/audit')
    ), (summary) => { taskDebtSummary.value = summary }, '后台任务状态加载失败')
  }

  async function loadAgentWorkflowSummary() {
    await loadWithState(agentWorkflowLoadState, async () => {
      const data = await api.post<unknown, AgentWorkflowListResponse>('/modules/call', {
        target_module: 'agent',
        action: 'list_workflows',
        parameters: { limit: 8 },
      })
      const items = data.items ?? []
      const needsConfirmationStatuses = new Set(['needs_confirmation', 'manual_required', 'waiting_approval'])
      const activeStatuses = new Set(['pending', 'running', 'in_progress', 'queued'])
      return {
        items,
        total: data.total ?? items.length,
        active_count: items.filter((item) => activeStatuses.has(item.status)).length,
        needs_confirmation_count: items.filter((item) => needsConfirmationStatuses.has(item.status)).length,
        failed_count: items.filter((item) => item.status === 'failed').length,
        partial_count: items.filter((item) => item.status === 'partial' || item.status === 'partial_completed').length,
      }
    }, (summary) => { agentWorkflowSummary.value = summary }, 'Agent 工作状态加载失败')
  }

  async function loadKnowledgeSignals() {
    await loadWithState(knowledgeStatsLoadState, async () => {
      const stats = await api.get<unknown, KnowledgeDashboardStats>('/knowledge/dashboard/stats')
      return {
        ...stats,
        stuck_documents: Array.isArray(stats.stuck_documents) ? stats.stuck_documents : [],
      }
    }, (stats) => { knowledgeStats.value = stats }, '知识库状态加载失败')
    await loadWithState(knowledgePendingLoadState, async () => {
      const pending = await api.get<unknown, KnowledgePendingCount>('/knowledge/governance/pending-count')
      return pending.pending_count
    }, (count) => { knowledgePendingCount.value = count }, '知识治理待办加载失败')
  }

  async function markRead(id: number) {
    try {
      await api.post(`/notifications/${id}/read`)
      const item = notificationList.value.find((n) => n.id === id)
      if (item) item.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch (error: unknown) {
      displayApiError(error, '通知标记失败')
    }
  }

  async function markAllRead() {
    try {
      await api.post('/notifications/read-all')
      notificationList.value.forEach((n) => { n.is_read = true })
      unreadCount.value = 0
    } catch (error: unknown) {
      displayApiError(error, '全部已读失败')
    }
  }

  async function retryFeedbackLoad(source?: NotificationLoadSource) {
    if (!source) {
      await Promise.all([
        loadUnreadCount(),
        loadNotificationList(),
        loadTaskDebtSummary(),
        loadAgentWorkflowSummary(),
        loadKnowledgeSignals(),
      ])
      return
    }
    if (source === 'unreadCount') await loadUnreadCount()
    else if (source === 'notifications') await loadNotificationList()
    else if (source === 'taskDebt') await loadTaskDebtSummary()
    else if (source === 'agentWorkflows') await loadAgentWorkflowSummary()
    else if (source === 'knowledgeStats' || source === 'knowledgeGovernance') await loadKnowledgeSignals()
  }

  function toggleNotificationPanel() {
    showNotificationPanel.value = !showNotificationPanel.value
    if (showNotificationPanel.value) {
      loadNotificationList()
      loadTaskDebtSummary()
      loadAgentWorkflowSummary()
      loadKnowledgeSignals()
    }
  }

  function dismissActionItem(id: string) {
    dismissedActionItemIds.value = new Set(dismissedActionItemIds.value).add(id)
  }

  function handleClickOutside(e: MouseEvent) {
    const target = e.target as HTMLElement
    if (!target.closest(containerSelector)) {
      showNotificationPanel.value = false
    }
  }

  onMounted(() => {
    loadUnreadCount()
    loadTaskDebtSummary()
    loadAgentWorkflowSummary()
    loadKnowledgeSignals()
    document.addEventListener('click', handleClickOutside)
  })

  onUnmounted(() => {
    document.removeEventListener('click', handleClickOutside)
  })

  function issueFromState<T>(source: NotificationLoadSource, state: LoadState<T>): NotificationLoadIssue | null {
    if (state.status !== 'error' && state.status !== 'stale') return null
    if (!state.error) return null
    const label = loadStateLabels[source]
    const statusLabel = state.status === 'stale' ? '可能不是最新' : '加载失败'
    const backendMessage = state.error.backendMessage
    return {
      source,
      label,
      status: state.status,
      message: state.error.userMessage,
      backendMessage,
      copyText: [
        `${label}${statusLabel}`,
        `用户提示：${state.error.userMessage}`,
        backendMessage ? `后端摘要：${backendMessage}` : '',
        state.error.code ? `错误码：${state.error.code}` : '',
        state.error.httpStatus !== undefined ? `HTTP：${state.error.httpStatus}` : '',
      ].filter(Boolean).join('\n'),
      sourceTarget: loadIssueTarget(source),
    }
  }

  return {
    unreadCount,
    notificationList,
    taskDebtSummary,
    agentWorkflowSummary,
    knowledgeStats,
    knowledgePendingCount,
    feedbackSignalCount,
    taskSignalCount,
    agentSignalCount,
    knowledgeSignalCount,
    feedbackLoadIssues,
    hasFeedbackLoadError,
    hasStaleFeedbackData,
    isFeedbackLoading,
    actionItems,
    showNotificationPanel,
    toggleNotificationPanel,
    loadUnreadCount,
    loadTaskDebtSummary,
    loadAgentWorkflowSummary,
    loadKnowledgeSignals,
    retryFeedbackLoad,
    markRead,
    markAllRead,
    dismissActionItem,
  }
}

function loadIssueTarget(source: NotificationLoadSource): ActionTarget | undefined {
  if (source === 'agentWorkflows') return { app_key: 'agent', payload: { view: 'workflows' } }
  if (source === 'knowledgeStats') return { app_key: 'knowledge', payload: { view: 'dashboard' } }
  if (source === 'knowledgeGovernance') return { app_key: 'knowledge', payload: { view: 'dashboard', showGovernance: true } }
  return undefined
}

async function loadWithState<T>(
  state: Ref<LoadState<T>>,
  loader: () => Promise<T>,
  apply: (data: T) => void,
  fallbackMessage: string,
): Promise<void> {
  startLoading(state)
  try {
    const data = await loader()
    apply(data)
    finishLoading(state, data)
  } catch (error: unknown) {
    failLoading(state, error, fallbackMessage)
  }
}

function notificationSeverity(type: string): ActionItemSeverity {
  const value = type.toLowerCase()
  if (value.includes('error') || value.includes('系统公告')) return 'error'
  if (value.includes('warning') || value.includes('维护')) return 'warning'
  if (value.includes('success')) return 'success'
  return 'info'
}

function modelFallbackDescription(notice: ModelFallbackNotice): string {
  const fallbackText = notice.fallbackUsed ? `已切到 ${notice.fallbackModel}` : '未使用 fallback'
  const finalText = notice.finalSuccess ? '最终成功' : '最终失败'
  const categoryText = notice.failureCategory ? `，原因 ${notice.failureCategory}` : ''
  return `主模型 ${notice.primaryModel} ${notice.primaryFailed ? '失败' : '异常'}，${fallbackText}，${finalText}${categoryText}。${notice.reason}`
}

function modelFallbackFromNotification(notification: NotificationItem): ModelFallbackNotice | null {
  const direct = normalizeModelFallbackNotice(recordField(notification, 'model_fallback'))
  if (direct) return direct

  const content = stringField(notification, 'content')
  const parsedContent = parseJsonObject(content)
  const fromContent = normalizeModelFallbackNotice(recordField(parsedContent, 'model_fallback') ?? parsedContent)
  if (fromContent) return fromContent

  const haystack = `${notification.title} ${notification.notification_type} ${content}`.toLowerCase()
  const mentionsModel = haystack.includes('model') || haystack.includes('模型') || haystack.includes('vlm') || haystack.includes('qwen') || haystack.includes('mimo')
  const mentionsFallback = haystack.includes('fallback') || haystack.includes('降级') || haystack.includes('degraded')
  if (!mentionsModel || !mentionsFallback) return null
  return {
    primaryModel: 'primary',
    fallbackModel: haystack.includes('local') || haystack.includes('本地') ? 'local_analysis' : 'fallback',
    primaryFailed: true,
    fallbackUsed: true,
    finalSuccess: !haystack.includes('最终失败') && !haystack.includes('final failed'),
    failureCategory: haystack.includes('401') || haystack.includes('auth') ? 'auth_config_debt'
      : haystack.includes('context') || haystack.includes('上下文') ? 'context_too_large'
        : 'model_unavailable',
    reason: content.slice(0, 160),
  }
}

function normalizeModelFallbackNotice(value: unknown): ModelFallbackNotice | null {
  if (!isRecord(value)) return null
  const primaryModel = stringField(value, 'primary_model') || stringField(value, 'primaryModel') || 'primary'
  const fallbackModel = stringField(value, 'fallback_model') || stringField(value, 'fallbackModel') || 'fallback'
  const primaryFailed = booleanField(value, 'primary_failed') ?? booleanField(value, 'primaryFailed') ?? true
  const fallbackUsed = booleanField(value, 'fallback_used') ?? booleanField(value, 'fallbackUsed') ?? false
  const finalSuccess = booleanField(value, 'final_success') ?? booleanField(value, 'finalSuccess') ?? false
  const failureCategory = stringField(value, 'failure_category') || stringField(value, 'failureCategory') || ''
  const failureCode = stringField(value, 'failure_code') || stringField(value, 'failureCode')
  const reason = stringField(value, 'summary') || stringField(value, 'reason') || stringField(value, 'message') || ''
  if (!primaryFailed && !fallbackUsed && !failureCategory) return null
  return {
    primaryModel,
    fallbackModel,
    primaryFailed,
    fallbackUsed,
    finalSuccess,
    failureCategory,
    failureCode,
    reason,
  }
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  const text = value.trim()
  if (!text) return null
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) return null
  try {
    const parsed: unknown = JSON.parse(text.slice(start, end + 1))
    return isRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

function recordField(record: Record<string, unknown> | NotificationItem | null, key: string): Record<string, unknown> | null {
  if (!record) return null
  const value = record[key]
  return isRecord(value) ? value : null
}

function stringField(record: Record<string, unknown> | NotificationItem, key: string): string {
  const value = record[key]
  return typeof value === 'string' ? value : ''
}

function booleanField(record: Record<string, unknown>, key: string): boolean | undefined {
  const value = record[key]
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') {
    if (['true', '1', 'yes'].includes(value.toLowerCase())) return true
    if (['false', '0', 'no'].includes(value.toLowerCase())) return false
  }
  return undefined
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function taskProblemCount(summary: TaskDebtSummary): number {
  return summary.summary.failed
    + summary.recent_failed_count
    + summary.historical_debt_total
    + summary.classification.stale_pending_debt_count
    + summary.classification.orphan_running_debt_count
    + summary.classification.completed_semantic_failure_count
}

function userStatusLabel(status: string): string {
  const value = status.toLowerCase()
  if (['pending', 'waiting', 'planned', 'queued'].includes(value)) return '等待中'
  if (['running', 'processing', 'in_progress'].includes(value)) return '处理中'
  if (['needs_confirmation', 'manual_required', 'waiting_approval', 'paused'].includes(value)) return '需要确认'
  if (['completed', 'done', 'pass', 'clean_completed'].includes(value)) return '已完成'
  if (['cancelled', 'canceled'].includes(value)) return '已取消'
  if (['failed', 'fail', 'blocked', 'rejected'].includes(value)) return '失败'
  return '部分完成'
}

function workflowDescription(status: string): string {
  if (status === '需要确认') return '继续执行前需要你确认下一步。'
  if (status === '失败') return '这项 Agent 工作失败了，需要查看原因或重新安排。'
  if (status === '部分完成') return '这项 Agent 工作有产物或验证未完全通过。'
  if (status === '处理中') return 'Agent 正在处理这项工作。'
  return '这项 Agent 工作等待继续处理。'
}
