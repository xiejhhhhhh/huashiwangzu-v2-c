<template>
  <div v-if="show" class="notification-panel">
    <div class="notification-panel-header">
      <span class="notification-panel-title">反馈中心</span>
      <el-tag :type="feedbackSignalCount === 0 ? 'success' : 'warning'" size="small">
        {{ feedbackSignalCount === 0 ? '一切正常' : `${feedbackSignalCount} 项` }}
      </el-tag>
    </div>

    <div v-if="hasActionItems" class="feedback-section">
      <div class="feedback-section-title">需要处理</div>
      <div v-if="agentNeedsConfirmation > 0" class="feedback-action-row urgent">
        <div>
          <div class="feedback-action-title">有 Agent 工作需要确认</div>
          <div class="feedback-action-copy">继续执行前需要你确认下一步。</div>
        </div>
        <button class="feedback-link" type="button" @click="emit('open-agent')">去 Agent 查看</button>
      </div>
      <div v-if="agentFailedOrPartial > 0" class="feedback-action-row warning">
        <div>
          <div class="feedback-action-title">有 Agent 工作未完全完成</div>
          <div class="feedback-action-copy">失败或部分完成的工作需要查看原因和产物状态。</div>
        </div>
        <button class="feedback-link" type="button" @click="emit('open-agent')">去 Agent 查看</button>
      </div>
      <div v-if="taskProblemTotal > 0" class="feedback-action-row warning">
        <div>
          <div class="feedback-action-title">后台任务有失败或债务</div>
          <div class="feedback-action-copy">失败 {{ taskDebtSummary?.summary.failed ?? 0 }}，近期失败 {{ taskDebtSummary?.classification.recent_failed_count ?? 0 }}，历史债务 {{ taskDebtSummary?.historical_debt_total ?? 0 }}。</div>
        </div>
      </div>
    </div>

    <div v-if="taskDebtSummary" class="task-debt-summary" :class="{ 'task-debt-summary-clean': taskSignalTotal === 0 }">
      <div class="task-debt-title-row">
        <span class="task-debt-title">后台任务</span>
        <el-tag :type="taskSignalTotal === 0 ? 'success' : taskProblemTotal > 0 ? 'warning' : 'primary'" size="small">
          {{ taskStatusText }}
        </el-tag>
      </div>
      <div class="task-debt-metrics">
        <span>等待中 {{ taskDebtSummary.summary.pending }}</span>
        <span>处理中 {{ taskDebtSummary.summary.running }}</span>
        <span>已完成 {{ taskDebtSummary.summary.completed }}</span>
        <span>失败 {{ taskDebtSummary.summary.failed }}</span>
      </div>
      <div v-if="taskProblemTotal > 0" class="task-debt-hint">
        这些任务没有自动清理或重试，请到对应模块查看详情。
      </div>
    </div>

    <div v-if="agentWorkflowSummary" class="feedback-section">
      <div class="feedback-section-title">Agent 工作</div>
      <div class="task-debt-metrics">
        <span>处理中 {{ agentWorkflowSummary.active_count }}</span>
        <span>需要确认 {{ agentWorkflowSummary.needs_confirmation_count }}</span>
        <span>失败 {{ agentWorkflowSummary.failed_count }}</span>
        <span>部分完成 {{ agentWorkflowSummary.partial_count }}</span>
      </div>
      <div v-if="agentWorkflowSummary.items.length" class="workflow-list">
        <div v-for="workflow in agentWorkflowSummary.items.slice(0, 3)" :key="workflow.id" class="workflow-row">
          <span class="workflow-title">{{ workflow.title || `Agent 工作 #${workflow.id}` }}</span>
          <span class="workflow-status">{{ userStatusLabel(workflow.status) }}</span>
        </div>
      </div>
      <button class="feedback-link inline" type="button" @click="emit('open-agent')">去 Agent 查看</button>
    </div>

    <div v-if="isEmpty" class="notification-empty">
      <div class="empty-title">现在没有需要处理的反馈</div>
      <div class="empty-copy">后台任务、通知和 Agent 工作有新进展时会显示在这里。</div>
    </div>

    <div v-if="items.length > 0" class="feedback-section-title notification-list-title">通知</div>
    <div v-for="item in items" :key="item.id" class="notification-item" :class="{ 'notification-item-unread': !item.is_read }">
      <div class="notification-item-content">
        <div class="notification-title-row">
          <span class="notification-title" :class="{ 'notification-title-unread': !item.is_read }">{{ item.title }}</span>
          <el-tag :type="tagType(item.notification_type)" size="small" class="notification-tag">{{ item.notification_type }}</el-tag>
        </div>
        <div class="notification-time">{{ item.published_at }}</div>
      </div>
      <div class="notification-actions">
        <span v-if="!item.is_read" class="notification-mark-read" @click.stop="handleMarkRead(item.id)">标为已读</span>
        <span v-else class="notification-read-label">✓ 已读</span>
      </div>
    </div>
    <div v-if="items.length > 0" class="notification-panel-footer">
      <el-button text size="small" @click="handleMarkAllRead">全部已读</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { NotificationItem } from '@/shared/api/types'
import type { AgentWorkflowSummary, TaskDebtSummary } from '@/shared/composables/use-notifications'
import { computed } from 'vue'

const props = defineProps<{
 show: boolean
 items: NotificationItem[]
 taskDebtSummary?: TaskDebtSummary | null
 agentWorkflowSummary?: AgentWorkflowSummary | null
 feedbackSignalCount?: number
}>()

const emit = defineEmits<{
  'mark-read': [id: number]
  'mark-all-read': []
  'open-agent': []
}>()

function tagType(type: string) {
  const typeMap: Record<string, string> = {
    '系统公告': 'danger',
    '维护通知': 'warning',
    '更新日志': 'primary',
    '普通通知': 'info',
    error: 'danger',
    warning: 'warning',
    success: 'success',
    info: 'info',
  }
  return typeMap[type] || 'info'
}

const debtTotal = computed(() => {
  const summary = props.taskDebtSummary
  if (!summary) return 0
  return summary.recent_failed_count
    + summary.historical_debt_total
    + summary.classification.stale_pending_debt_count
    + summary.classification.orphan_running_debt_count
    + summary.classification.completed_semantic_failure_count
})

const feedbackSignalCount = computed(() => props.feedbackSignalCount ?? 0)
const taskSignalTotal = computed(() => {
  const summary = props.taskDebtSummary
  if (!summary) return 0
  return summary.summary.pending + summary.summary.running + debtTotal.value
})
const taskProblemTotal = computed(() => {
  const summary = props.taskDebtSummary
  if (!summary) return 0
  return summary.summary.failed
    + summary.recent_failed_count
    + summary.historical_debt_total
    + summary.classification.stale_pending_debt_count
    + summary.classification.orphan_running_debt_count
    + summary.classification.completed_semantic_failure_count
})
const agentNeedsConfirmation = computed(() => props.agentWorkflowSummary?.needs_confirmation_count ?? 0)
const agentFailedOrPartial = computed(() => {
  const summary = props.agentWorkflowSummary
  if (!summary) return 0
  return summary.failed_count + summary.partial_count
})
const hasActionItems = computed(() => agentNeedsConfirmation.value + agentFailedOrPartial.value + taskProblemTotal.value > 0)
const isEmpty = computed(() => props.items.length === 0 && taskSignalTotal.value === 0 && (props.agentWorkflowSummary?.total ?? 0) === 0)
const taskStatusText = computed(() => {
  if (taskProblemTotal.value > 0) return '部分完成'
  if ((props.taskDebtSummary?.summary.running ?? 0) > 0) return '处理中'
  if ((props.taskDebtSummary?.summary.pending ?? 0) > 0) return '等待中'
  return '已完成'
})

function userStatusLabel(status: string) {
  const value = status.toLowerCase()
  if (['pending', 'waiting', 'planned', 'queued'].includes(value)) return '等待中'
  if (['running', 'processing', 'in_progress'].includes(value)) return '处理中'
  if (['needs_confirmation', 'manual_required', 'waiting_approval', 'paused'].includes(value)) return '需要确认'
  if (['completed', 'done', 'pass', 'clean_completed'].includes(value)) return '已完成'
  if (['failed', 'fail', 'blocked', 'rejected'].includes(value)) return '失败'
  return '部分完成'
}

function handleMarkRead(id: number) {
  emit('mark-read', id)
}

function handleMarkAllRead() {
  emit('mark-all-read')
}
</script>

<style scoped>
.notification-panel-header {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f0f0f0;
}

.notification-panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.feedback-section {
  margin: 10px 12px;
  padding: 10px 12px;
  border: 1px solid #e3e9f2;
  border-radius: 6px;
  background: #fff;
}

.feedback-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #46586b;
  margin-bottom: 8px;
}

.notification-list-title {
  margin: 12px 16px 0;
}

.feedback-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
}

.feedback-action-row + .feedback-action-row {
  border-top: 1px solid #f0f3f7;
}

.feedback-action-row.urgent .feedback-action-title {
  color: #9a6700;
}

.feedback-action-row.warning .feedback-action-title {
  color: #b45309;
}

.feedback-action-title {
  font-size: 13px;
  font-weight: 700;
}

.feedback-action-copy {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
}

.feedback-link {
  flex: none;
  border: 1px solid #bcd6e6;
  border-radius: 6px;
  background: #f7fbfe;
  color: #1f86a9;
  cursor: pointer;
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 600;
}

.feedback-link:hover {
  border-color: #2395bc;
  background: #eaf6fb;
}

.feedback-link.inline {
  margin-top: 8px;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid #f5f5f5;
  transition: background 0.15s;
}

.task-debt-summary {
  margin: 10px 12px;
  padding: 10px 12px;
  border: 1px solid #f2d18b;
  border-radius: 6px;
  background: #fff8e6;
}

.task-debt-summary-clean {
  border-color: #b7e4c7;
  background: #f0fdf4;
}

.task-debt-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.task-debt-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.task-debt-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.task-debt-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #9a6700;
}

.workflow-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.workflow-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.workflow-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.workflow-status {
  flex: none;
  color: #1f86a9;
  font-weight: 600;
}

.notification-item:hover {
  background: #f6f8fa;
}

.notification-item:last-child {
  border-bottom: none;
}

.notification-item-unread {
  background: var(--primary-color-light);
}

.notification-item-content {
  flex: 1;
  min-width: 0;
}

.notification-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.notification-title {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.notification-title-unread {
  font-weight: 600;
}

.notification-tag {
  flex-shrink: 0;
}

.notification-time {
  font-size: 12px;
  color: var(--text-placeholder);
}

.notification-actions {
  flex-shrink: 0;
  margin-left: 12px;
  padding-top: 2px;
}

.notification-mark-read {
  font-size: 12px;
  color: var(--primary-color);
  cursor: pointer;
  white-space: nowrap;
}

.notification-mark-read:hover {
  color: var(--primary-color-dark);
}

.notification-read-label {
  font-size: 12px;
  color: var(--text-placeholder);
  white-space: nowrap;
}

.notification-empty {
  padding: 28px 18px;
  text-align: center;
}

.empty-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.empty-copy {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.notification-panel-footer {
  padding: 10px 16px;
  border-top: 1px solid #f0f0f0;
  text-align: center;
}
</style>
