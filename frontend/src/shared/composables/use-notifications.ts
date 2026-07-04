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

export function useNotifications(containerSelector = '.taskbar-notifications-wrapper') {
  const unreadCount = ref(0)
  const notificationList = ref<NotificationItem[]>([])
  const taskDebtSummary = ref<TaskDebtSummary | null>(null)
  const agentWorkflowSummary = ref<AgentWorkflowSummary | null>(null)
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

  const feedbackSignalCount = computed(() => unreadCount.value + taskSignalCount.value + agentSignalCount.value)

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
    }
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
    feedbackSignalCount,
    taskSignalCount,
    agentSignalCount,
    showNotificationPanel,
    toggleNotificationPanel,
    loadUnreadCount,
    loadTaskDebtSummary,
    loadAgentWorkflowSummary,
    markRead,
    markAllRead,
  }
}
