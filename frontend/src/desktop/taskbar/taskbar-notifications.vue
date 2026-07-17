<template>
  <div class="taskbar-notifications-wrapper" ref="notificationContainer">
    <el-badge :value="feedbackSignalCount" :hidden="feedbackSignalCount === 0" class="taskbar-notifications-badge">
      <button
        ref="notificationButton"
        class="taskbar-notifications-button"
        :class="buttonStatusClass"
        type="button"
        :title="buttonTitle"
        aria-label="打开反馈中心"
        :aria-expanded="showNotificationPanel ? 'true' : 'false'"
        aria-controls="taskbar-notifications-panel"
        @click.stop="handleToggleNotificationPanel"
      >
        <el-icon :size="18"><Bell /></el-icon>
      </button>
    </el-badge>
    <div
      v-if="showNotificationPanel"
      id="taskbar-notifications-panel"
      ref="notificationPanel"
      class="taskbar-notifications-panel"
      tabindex="-1"
      @click.stop
      @keydown.esc.stop.prevent="closeNotificationPanel"
    >
      <NotifyPanel
        :show="showNotificationPanel"
        :items="notificationList"
        :task-debt-summary="taskDebtSummary"
        :agent-workflow-summary="agentWorkflowSummary"
        :action-items="actionItems"
        :feedback-signal-count="feedbackSignalCount"
        :load-issues="feedbackLoadIssues"
        :is-loading="isFeedbackLoading"
        @mark-read="markRead"
        @mark-all-read="markAllRead"
        @action-primary="handleActionPrimary"
        @action-secondary="handleActionSecondary"
        @open-agent="emit('open-app', 'agent')"
        @retry-load="retryFeedbackLoad"
        @open-load-source="handleOpenLoadSource"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bell } from '@element-plus/icons-vue'
import { useNotifications } from '@/shared/composables/use-notifications'
import type { ActionItem, NotificationLoadIssue } from '@/shared/composables/use-notifications'
import NotifyPanel from '@/shared/components/notification-panel.vue'
import { computed, nextTick, ref } from 'vue'

const emit = defineEmits<{
  'open-app': [id: string, payload?: Record<string, unknown>]
}>()

const {
  unreadCount,
  notificationList,
  taskDebtSummary,
  agentWorkflowSummary,
  actionItems,
  feedbackSignalCount,
  feedbackLoadIssues,
  hasFeedbackLoadError,
  hasStaleFeedbackData,
  isFeedbackLoading,
  showNotificationPanel,
  toggleNotificationPanel,
  markRead,
  markAllRead,
  dismissActionItem,
  retryFeedbackLoad,
} = useNotifications()

const notificationButton = ref<HTMLButtonElement | null>(null)
const notificationPanel = ref<HTMLElement | null>(null)

const buttonTitle = computed(() => {
  if (hasFeedbackLoadError.value) return '反馈中心加载失败'
  if (hasStaleFeedbackData.value) return '反馈中心数据可能不是最新'
  const workflow = agentWorkflowSummary.value
  const tasks = taskDebtSummary.value
  if (workflow && workflow.needs_confirmation_count > 0) return '有事项需要确认'
  if (workflow && workflow.failed_count + workflow.partial_count > 0) return '有 Agent 工作需要查看'
  if (tasks && tasks.summary.failed + tasks.recent_failed_count + tasks.historical_debt_total > 0) return '有后台任务失败'
  if (tasks && tasks.summary.running + tasks.summary.pending > 0) return '后台任务处理中'
  if (unreadCount.value > 0) return '有未读通知'
  return '反馈中心'
})

const buttonStatusClass = computed(() => {
  if (hasFeedbackLoadError.value) return 'status-failed'
  if (hasStaleFeedbackData.value) return 'status-partial'
  const workflow = agentWorkflowSummary.value
  const tasks = taskDebtSummary.value
  if ((workflow && workflow.failed_count > 0) || (tasks && tasks.summary.failed + tasks.recent_failed_count > 0)) {
    return 'status-failed'
  }
  if (workflow && workflow.needs_confirmation_count > 0) return 'status-confirm'
  if ((workflow && workflow.partial_count > 0) || (tasks && tasks.historical_debt_total > 0)) return 'status-partial'
  if ((workflow && workflow.active_count > 0) || (tasks && tasks.summary.running + tasks.summary.pending > 0)) return 'status-processing'
  return ''
})

async function handleToggleNotificationPanel() {
  toggleNotificationPanel()
  if (showNotificationPanel.value) {
    await nextTick()
    notificationPanel.value?.focus()
  }
}

function closeNotificationPanel() {
  if (!showNotificationPanel.value) return
  showNotificationPanel.value = false
  void nextTick(() => notificationButton.value?.focus())
}

function handleActionPrimary(item: ActionItem) {
  if (item.source_type === 'notification') {
    void markRead(Number(item.source_id))
    return
  }
  if (item.action_target) {
    emit('open-app', item.action_target.app_key, item.action_target.payload)
  }
}

function handleActionSecondary(item: ActionItem, actionId: string) {
  if (item.source_type === 'notification' && actionId === 'archive') {
    void markRead(Number(item.source_id))
    return
  }
  dismissActionItem(item.id)
}

function handleOpenLoadSource(issue: NotificationLoadIssue) {
  if (!issue.sourceTarget) return
  emit('open-app', issue.sourceTarget.app_key, issue.sourceTarget.payload)
}
</script>

<style scoped>
.taskbar-notifications-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}
.taskbar-notifications-badge :deep(.el-badge__content) {
  font-size: 10px;
  height: 16px;
  line-height: 16px;
  padding: 0 5px;
  border: none;
  box-shadow: 0 0 0 2px rgba(15, 23, 42, 0.44);
}
.taskbar-notifications-button {
  position: relative;
  width: 28px;
  height: 22px;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  cursor: pointer;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: .86;
  transition: background .16s ease, border-color .16s ease, box-shadow .16s ease, opacity .16s ease, transform .16s ease;
}
.taskbar-notifications-button::after {
  content: '';
  position: absolute;
  right: 5px;
  bottom: 5px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: transparent;
  box-shadow: 0 0 0 2px rgba(15, 23, 42, 0.36);
}
.taskbar-notifications-button:hover {
  background: rgba(255,255,255,.2);
  border-color: rgba(255,255,255,.14);
  opacity: 1;
  transform: none;
}
.taskbar-notifications-button:focus-visible {
  outline: 2px solid rgba(191, 219, 254, .9);
  outline-offset: 2px;
}
.taskbar-notifications-button.status-failed {
  color: #fecaca;
  background: rgba(239, 68, 68, .18);
  box-shadow: inset 0 0 0 1px rgba(248, 113, 113, .18);
}
.taskbar-notifications-button.status-failed::after { background: #ef4444; }
.taskbar-notifications-button.status-confirm {
  color: #fde68a;
  background: rgba(245, 158, 11, .18);
  box-shadow: inset 0 0 0 1px rgba(251, 191, 36, .18);
}
.taskbar-notifications-button.status-confirm::after { background: #f59e0b; }
.taskbar-notifications-button.status-partial {
  color: #fed7aa;
  background: rgba(249, 115, 22, .16);
  box-shadow: inset 0 0 0 1px rgba(251, 146, 60, .18);
}
.taskbar-notifications-button.status-partial::after { background: #f97316; }
.taskbar-notifications-button.status-processing {
  color: #bae6fd;
  background: rgba(14, 165, 233, .16);
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, .18);
}
.taskbar-notifications-button.status-processing::after { background: #38bdf8; }
.taskbar-notifications-panel {
  position: fixed;
  top: 30px;
  right: 8px;
  bottom: auto;
  width: min(380px, calc(100vw - 24px));
  max-height: min(560px, calc(100vh - 72px));
  overflow-y: auto;
  background: var(--desktop-material-popover);
  border: 1px solid var(--desktop-material-border);
  border-radius: var(--desktop-radius-popover);
  box-shadow: var(--desktop-shadow-popover);
  backdrop-filter: blur(24px) saturate(160%);
  z-index: var(--z-system-popover);
}
</style>
