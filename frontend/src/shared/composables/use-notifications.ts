import { computed, ref, onMounted, onUnmounted } from 'vue'
import api from '@/shared/api'
import type { NotificationItem } from '@/shared/api/types'

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

export type ActionItemSourceType = 'notification' | 'task' | 'agent_workflow' | 'knowledge_document' | 'knowledge_governance'
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

export function useNotifications(containerSelector = '.taskbar-notifications-wrapper') {
  const unreadCount = ref(0)
  const notificationList = ref<NotificationItem[]>([])
  const taskDebtSummary = ref<TaskDebtSummary | null>(null)
  const agentWorkflowSummary = ref<AgentWorkflowSummary | null>(null)
  const knowledgeStats = ref<KnowledgeDashboardStats | null>(null)
  const knowledgePendingCount = ref(0)
  const dismissedActionItemIds = ref<Set<string>>(new Set())
  const showNotificationPanel = ref(false)

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
    try {
      const data = await api.get<unknown, { unread_count: number }>('/notifications/unread-count')
      unreadCount.value = data.unread_count
    } catch {
      unreadCount.value = 0
    }
  }

  async function loadNotificationList() {
    try {
      const data = await api.get<unknown, { list: NotificationItem[] }>('/notifications')
      notificationList.value = data.list
    } catch {
      notificationList.value = []
    }
  }

  async function loadTaskDebtSummary() {
    try {
      taskDebtSummary.value = await api.get<unknown, TaskDebtSummary>('/tasks/worker/audit')
    } catch {
      taskDebtSummary.value = null
    }
  }

  async function loadAgentWorkflowSummary() {
    try {
      const data = await api.post<unknown, AgentWorkflowListResponse>('/modules/call', {
        target_module: 'agent',
        action: 'list_workflows',
        parameters: { limit: 8 },
      })
      const items = data.items ?? []
      const needsConfirmationStatuses = new Set(['needs_confirmation', 'manual_required', 'waiting_approval'])
      const activeStatuses = new Set(['pending', 'running', 'in_progress', 'queued'])
      agentWorkflowSummary.value = {
        items,
        total: data.total ?? items.length,
        active_count: items.filter((item) => activeStatuses.has(item.status)).length,
        needs_confirmation_count: items.filter((item) => needsConfirmationStatuses.has(item.status)).length,
        failed_count: items.filter((item) => item.status === 'failed').length,
        partial_count: items.filter((item) => item.status === 'partial' || item.status === 'partial_completed').length,
      }
    } catch {
      agentWorkflowSummary.value = null
    }
  }

  async function loadKnowledgeSignals() {
    try {
      knowledgeStats.value = await api.get<unknown, KnowledgeDashboardStats>('/knowledge/dashboard/stats')
    } catch {
      knowledgeStats.value = null
    }
    try {
      const pending = await api.get<unknown, KnowledgePendingCount>('/knowledge/governance/pending-count')
      knowledgePendingCount.value = pending.pending_count
    } catch {
      knowledgePendingCount.value = 0
    }
  }

  async function markRead(id: number) {
    try {
      await api.post(`/notifications/${id}/read`)
      const item = notificationList.value.find((n) => n.id === id)
      if (item) item.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch {
      console.warn('[Notifications] Failed to mark notification as read.')
    }
  }

  async function markAllRead() {
    try {
      await api.post('/notifications/read-all')
      notificationList.value.forEach((n) => { n.is_read = true })
      unreadCount.value = 0
    } catch {
      console.warn('[Notifications] Failed to mark all notifications as read.')
    }
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
    actionItems,
    showNotificationPanel,
    toggleNotificationPanel,
    loadUnreadCount,
    loadTaskDebtSummary,
    loadAgentWorkflowSummary,
    loadKnowledgeSignals,
    markRead,
    markAllRead,
    dismissActionItem,
  }
}

function notificationSeverity(type: string): ActionItemSeverity {
  const value = type.toLowerCase()
  if (value.includes('error') || value.includes('系统公告')) return 'error'
  if (value.includes('warning') || value.includes('维护')) return 'warning'
  if (value.includes('success')) return 'success'
  return 'info'
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
