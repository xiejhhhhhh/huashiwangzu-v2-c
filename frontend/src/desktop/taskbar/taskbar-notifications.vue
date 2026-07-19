<template>
  <div class="taskbar-notifications-wrapper" ref="notificationContainer">
    <button
      ref="notificationButton"
      class="taskbar-notifications-button"
      :class="buttonStatusClass"
      type="button"
      :title="buttonTitle"
      aria-label="打开通知中心"
      :aria-expanded="showNotificationPanel ? 'true' : 'false'"
      aria-controls="taskbar-notifications-panel"
      @click.stop="handleToggleNotificationPanel"
    >
      <Bell :size="14" :stroke-width="2" />
      <span v-if="feedbackSignalCount > 0" class="taskbar-notifications-count">{{ feedbackSignalCount > 99 ? '99+' : feedbackSignalCount }}</span>
    </button>
    <div
      v-if="showNotificationPanel"
      id="taskbar-notifications-panel"
      ref="notificationPanel"
      class="taskbar-notifications-panel glass-panel"
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
import { Bell } from 'lucide-vue-next'
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
  if (hasFeedbackLoadError.value) return '通知中心加载失败'
  if (hasStaleFeedbackData.value) return '通知中心数据可能不是最新'
  const workflow = agentWorkflowSummary.value
  const tasks = taskDebtSummary.value
  if (workflow && (workflow.needs_confirmation_count || 0) > 0) return '有事项需要确认'
  if (workflow && ((workflow.failed_count || 0) + (workflow.partial_count || 0)) > 0) return '有 Agent 工作需要查看'
  if (tasks && ((tasks.summary?.failed || 0) + (tasks.recent_failed_count || 0) + (tasks.historical_debt_total || 0)) > 0) return '有后台任务失败'
  if (tasks && ((tasks.summary?.running || 0) + (tasks.summary?.pending || 0)) > 0) return '后台任务处理中'
  if (unreadCount.value > 0) return '有未读通知'
  return '通知中心'
})

const buttonStatusClass = computed(() => {
  if (hasFeedbackLoadError.value) return 'status-failed'
  if (hasStaleFeedbackData.value) return 'status-partial'
  const workflow = agentWorkflowSummary.value
  const tasks = taskDebtSummary.value
  if ((workflow && (workflow.failed_count || 0) > 0) || (tasks && ((tasks.summary?.failed || 0) + (tasks.recent_failed_count || 0)) > 0)) {
    return 'status-failed'
  }
  if (workflow && (workflow.needs_confirmation_count || 0) > 0) return 'status-confirm'
  if ((workflow && (workflow.partial_count || 0) > 0) || (tasks && (tasks.historical_debt_total || 0) > 0)) return 'status-partial'
  if ((workflow && (workflow.active_count || 0) > 0) || (tasks && ((tasks.summary?.running || 0) + (tasks.summary?.pending || 0)) > 0)) return 'status-processing'
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
.taskbar-notifications-button {
  position: relative;
  width: 28px;
  height: 22px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: default;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.96;
  transition: background 80ms ease, opacity 80ms ease;
}
.taskbar-notifications-count {
  position: absolute;
  top: -3px;
  right: -2px;
  min-width: 12px;
  height: 12px;
  padding: 0 3px;
  border-radius: 999px;
  background: #ff3b30;
  color: white;
  font: 600 9px/12px -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12);
}
.taskbar-notifications-button:hover {
  background: rgba(255, 255, 255, 0.14);
  opacity: 1;
}
:global(.mac-menu-bar.is-solid) .taskbar-notifications-button:hover {
  background: rgba(0, 0, 0, 0.06);
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
.taskbar-notifications-button.status-confirm {
  color: #fde68a;
  background: rgba(245, 158, 11, .18);
  box-shadow: inset 0 0 0 1px rgba(251, 191, 36, .18);
}
.taskbar-notifications-button.status-partial {
  color: #fed7aa;
  background: rgba(249, 115, 22, .16);
  box-shadow: inset 0 0 0 1px rgba(251, 146, 60, .18);
}
.taskbar-notifications-button.status-processing {
  color: #bae6fd;
  background: rgba(14, 165, 233, .16);
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, .18);
}
.taskbar-notifications-panel {
  position: fixed;
  top: calc(var(--desktop-menu-bar-height, 28px) + 8px);
  right: 12px;
  width: min(380px, calc(100vw - 24px));
  max-height: min(72vh, 640px);
  overflow: auto;
  transform: translateX(8px);
  animation: nc-slide-in 180ms cubic-bezier(.32,.72,0,1) forwards;
  z-index: var(--z-system-popover);
}
@keyframes nc-slide-in {
  from { opacity: 0; transform: translateX(18px); }
  to { opacity: 1; transform: translateX(0); }
}
</style>
