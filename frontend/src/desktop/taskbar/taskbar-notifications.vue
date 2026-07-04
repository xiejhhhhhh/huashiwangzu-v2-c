<template>
  <div class="taskbar-notifications-wrapper" ref="notificationContainer">
    <el-badge :value="feedbackSignalCount" :hidden="feedbackSignalCount === 0" class="taskbar-notifications-badge">
      <button
        class="taskbar-notifications-button"
        :class="buttonStatusClass"
        type="button"
        :title="buttonTitle"
        @click.stop="toggleNotificationPanel"
      >
        <el-icon :size="18"><Bell /></el-icon>
      </button>
    </el-badge>
    <div v-if="showNotificationPanel" class="taskbar-notifications-panel" @click.stop>
      <NotifyPanel
        :show="showNotificationPanel"
        :items="notificationList"
        :task-debt-summary="taskDebtSummary"
        :agent-workflow-summary="agentWorkflowSummary"
        :action-items="actionItems"
        :feedback-signal-count="feedbackSignalCount"
        @mark-read="markRead"
        @mark-all-read="markAllRead"
        @action-primary="handleActionPrimary"
        @action-secondary="handleActionSecondary"
        @open-agent="emit('open-app', 'agent')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bell } from '@element-plus/icons-vue'
import { useNotifications } from '@/shared/composables/use-notifications'
import type { ActionItem } from '@/shared/composables/use-notifications'
import NotifyPanel from '@/shared/components/notification-panel.vue'
import { computed } from 'vue'

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
  showNotificationPanel,
  toggleNotificationPanel,
  markRead,
  markAllRead,
  dismissActionItem,
} = useNotifications()

const buttonTitle = computed(() => {
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
}
.taskbar-notifications-button {
  width: 28px; height: 28px; border: none; background: transparent;
  color: #dbeafe; cursor: pointer; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  opacity: .82; transition: background .12s, opacity .12s;
}
.taskbar-notifications-button:hover { background: rgba(255,255,255,.08); opacity: 1; }
.taskbar-notifications-button.status-failed { color: #fecaca; background: rgba(239, 68, 68, .16); }
.taskbar-notifications-button.status-confirm { color: #fde68a; background: rgba(245, 158, 11, .16); }
.taskbar-notifications-button.status-partial { color: #fed7aa; background: rgba(249, 115, 22, .14); }
.taskbar-notifications-button.status-processing { color: #bae6fd; background: rgba(14, 165, 233, .14); }
.taskbar-notifications-panel {
  position: absolute;
  bottom: 44px;
  right: 0;
  width: 340px;
  max-height: 440px;
  overflow-y: auto;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  z-index: 11000;
}
</style>
