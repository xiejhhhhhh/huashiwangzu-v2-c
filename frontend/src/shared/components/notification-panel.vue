<template>
  <div
    v-if="show"
    class="notification-panel"
    role="dialog"
    aria-labelledby="notification-panel-title"
    :aria-busy="isLoading ? 'true' : 'false'"
  >
    <div class="notification-panel-header">
      <div class="notification-panel-heading">
        <span id="notification-panel-title" class="notification-panel-title">反馈中心</span>
        <span class="notification-panel-subtitle">主反馈、任务、Agent 与知识库状态</span>
      </div>
      <el-tag :type="panelTagType" size="small">
        {{ panelStatusText }}
      </el-tag>
    </div>

    <div v-if="loadIssues.length" class="feedback-load-section" aria-label="加载异常">
      <div class="feedback-section-title feedback-section-title-alert">错误与数据债务</div>
      <div
        v-for="issue in loadIssues"
        :key="issue.source"
        class="feedback-load-row"
        :class="{ 'feedback-load-row-stale': issue.status === 'stale' }"
      >
        <div class="feedback-load-copy">
          <span class="feedback-load-title">
            {{ issue.label }}{{ issue.status === 'stale' ? '可能不是最新' : '加载失败' }}
          </span>
          <span class="feedback-load-message">{{ issue.message }}</span>
          <span v-if="issue.backendMessage && issue.backendMessage !== issue.message" class="feedback-load-detail">
            {{ issue.backendMessage }}
          </span>
        </div>
        <div class="feedback-load-actions">
          <button
            class="feedback-load-retry"
            type="button"
            :aria-label="`复制${issue.label}错误`"
            @click="copyLoadIssue(issue)"
          >
            <el-icon :size="14"><CopyDocument /></el-icon>
            <span>复制</span>
          </button>
          <button
            v-if="issue.sourceTarget"
            class="feedback-load-retry"
            type="button"
            :aria-label="`打开${issue.label}来源`"
            @click="emit('open-load-source', issue)"
          >
            <el-icon :size="14"><Position /></el-icon>
            <span>来源</span>
          </button>
          <button
            class="feedback-load-retry"
            type="button"
            :aria-label="`重试${issue.label}`"
            @click="emit('retry-load', issue.source)"
          >
            <el-icon :size="14"><Refresh /></el-icon>
            <span>重试</span>
          </button>
        </div>
      </div>
      <button v-if="loadIssues.length > 1" class="feedback-load-retry all" type="button" @click="emit('retry-load')">
        <el-icon :size="14"><Refresh /></el-icon>
        <span>全部重试</span>
      </button>
    </div>

    <div v-else-if="isLoading" class="feedback-loading-section" role="status">
      <span class="feedback-loading-dot" aria-hidden="true" />
      <span>正在刷新反馈中心状态</span>
    </div>

    <div v-if="actionGroups.length" class="feedback-stack">
      <section
        v-for="group in actionGroups"
        :key="group.key"
        class="feedback-section feedback-action-group"
        :class="group.className"
        :aria-label="group.title"
      >
        <div class="feedback-section-heading">
          <div>
            <div class="feedback-section-title">{{ group.title }}</div>
            <div class="feedback-section-summary">{{ group.summary }}</div>
          </div>
          <span class="feedback-section-count">{{ group.items.length }}</span>
        </div>
        <div
          v-for="actionItem in group.items"
          :key="actionItem.id"
          class="feedback-action-row"
          :class="actionItemClass(actionItem)"
        >
          <div class="feedback-action-body">
            <div class="feedback-action-title-row">
              <span class="feedback-action-title">{{ actionItem.title }}</span>
              <el-tag :type="actionItemTagType(actionItem)" size="small">{{ actionItem.visible_status }}</el-tag>
            </div>
            <div class="feedback-action-copy">{{ actionItem.description }}</div>
            <div v-if="actionItem.secondary_actions.length" class="feedback-secondary-actions">
              <button
                v-for="secondary in actionItem.secondary_actions"
                :key="secondary.id"
                class="feedback-secondary-link"
                type="button"
                @click="emit('action-secondary', actionItem, secondary.id)"
              >
                {{ secondary.label }}
              </button>
            </div>
          </div>
          <button
            v-if="actionItem.action_label"
            class="feedback-link"
            type="button"
            @click="emit('action-primary', actionItem)"
          >
            {{ actionItem.action_label }}
          </button>
        </div>
      </section>
    </div>

    <div v-if="taskDebtSummary" class="task-debt-summary" :class="{ 'task-debt-summary-clean': taskSignalTotal === 0 }">
      <div class="task-debt-title-row">
        <div>
          <span class="task-debt-title">后台任务</span>
          <div class="task-debt-caption">{{ taskProblemTotal > 0 ? '失败、卡住与历史债务' : '队列运行状态' }}</div>
        </div>
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

    <div v-if="agentWorkflowSummary" class="feedback-section feedback-agent-section">
      <div class="feedback-section-heading">
        <div>
          <div class="feedback-section-title">Agent 工作</div>
          <div class="feedback-section-summary">执行中、待确认与部分完成事项</div>
        </div>
        <button class="feedback-link inline" type="button" @click="emit('open-agent')">去 Agent 查看</button>
      </div>
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
    </div>

    <div v-if="isEmpty" class="notification-empty" role="status">
      <div class="notification-empty-mark" aria-hidden="true">✓</div>
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
        <button v-if="!item.is_read" class="notification-mark-read" type="button" @click.stop="handleMarkRead(item.id)">标为已读</button>
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
import type {
  ActionItem,
  AgentWorkflowSummary,
  NotificationLoadIssue,
  NotificationLoadSource,
  TaskDebtSummary,
} from '@/shared/composables/use-notifications'
import { computed } from 'vue'
import { CopyDocument, Position, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
 show: boolean
 items: NotificationItem[]
  taskDebtSummary?: TaskDebtSummary | null
  agentWorkflowSummary?: AgentWorkflowSummary | null
  actionItems?: ActionItem[]
  feedbackSignalCount?: number
  loadIssues?: NotificationLoadIssue[]
  isLoading?: boolean
}>()

const emit = defineEmits<{
  'mark-read': [id: number]
  'mark-all-read': []
  'action-primary': [item: ActionItem]
  'action-secondary': [item: ActionItem, actionId: string]
  'open-agent': []
  'retry-load': [source?: NotificationLoadSource]
  'open-load-source': [issue: NotificationLoadIssue]
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
const actionItems = computed(() => props.actionItems ?? [])
const loadIssues = computed(() => props.loadIssues ?? [])
const hasLoadIssue = computed(() => loadIssues.value.length > 0)
type ActionGroupKey = 'primary' | 'task' | 'agent' | 'knowledge'
interface ActionGroup {
  key: ActionGroupKey
  title: string
  summary: string
  className: string
  items: ActionItem[]
}

const actionGroupMeta: Record<ActionGroupKey, Omit<ActionGroup, 'items'>> = {
  primary: {
    key: 'primary',
    title: '主反馈',
    summary: '系统通知与需要确认的即时反馈',
    className: 'feedback-action-group-primary',
  },
  task: {
    key: 'task',
    title: '任务',
    summary: '后台队列、失败任务与历史债务',
    className: 'feedback-action-group-task',
  },
  agent: {
    key: 'agent',
    title: 'Agent',
    summary: '需要查看、确认或继续的 Agent 工作',
    className: 'feedback-action-group-agent',
  },
  knowledge: {
    key: 'knowledge',
    title: 'Knowledge',
    summary: '知识库解析、治理和源文件状态',
    className: 'feedback-action-group-knowledge',
  },
}

const actionGroups = computed<ActionGroup[]>(() => {
  const grouped: Record<ActionGroupKey, ActionItem[]> = {
    primary: [],
    task: [],
    agent: [],
    knowledge: [],
  }
  for (const item of actionItems.value) {
    grouped[actionGroupKey(item)].push(item)
  }
  return (Object.keys(actionGroupMeta) as ActionGroupKey[])
    .filter((key) => grouped[key].length > 0)
    .map((key) => ({ ...actionGroupMeta[key], items: grouped[key] }))
})

const isEmpty = computed(() => (
  props.items.length === 0
  && taskSignalTotal.value === 0
  && (props.agentWorkflowSummary?.total ?? 0) === 0
  && actionItems.value.length === 0
  && !hasLoadIssue.value
  && !props.isLoading
))
const panelStatusText = computed(() => {
  if (hasLoadIssue.value) return '需重试'
  if (props.isLoading) return '加载中'
  return feedbackSignalCount.value === 0 ? '一切正常' : `${feedbackSignalCount.value} 项`
})
const panelTagType = computed(() => {
  if (hasLoadIssue.value) return 'danger'
  if (props.isLoading) return 'info'
  return feedbackSignalCount.value === 0 ? 'success' : 'warning'
})
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
  if (['cancelled', 'canceled'].includes(value)) return '已取消'
  if (['failed', 'fail', 'blocked', 'rejected'].includes(value)) return '失败'
  return '部分完成'
}

function actionItemClass(item: ActionItem): string {
  if (item.severity === 'error') return 'urgent'
  if (item.severity === 'warning') return 'warning'
  if (item.severity === 'success') return 'success'
  return 'info'
}

function actionItemTagType(item: ActionItem) {
  if (item.severity === 'error') return 'danger'
  if (item.severity === 'warning') return 'warning'
  if (item.severity === 'success') return 'success'
  return 'info'
}

function actionGroupKey(item: ActionItem): ActionGroupKey {
  if (item.source_type === 'task') return 'task'
  if (item.source_type === 'agent_workflow') return 'agent'
  if (item.source_type === 'knowledge_document' || item.source_type === 'knowledge_governance') return 'knowledge'
  return 'primary'
}

function handleMarkRead(id: number) {
  emit('mark-read', id)
}

function handleMarkAllRead() {
  emit('mark-all-read')
}

async function copyLoadIssue(issue: NotificationLoadIssue) {
  try {
    await navigator.clipboard.writeText(issue.copyText)
    ElMessage.success('错误信息已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择错误信息')
  }
}
</script>

<style scoped>
.notification-panel {
  min-height: 100%;
  padding-bottom: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(246, 248, 251, 0.98)),
    #f7f9fc;
  color: var(--text-primary);
}

.notification-panel-header {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 14px 16px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(18px);
}

.notification-panel-heading {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.notification-panel-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
}

.notification-panel-subtitle {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #64748b;
}

.feedback-stack {
  display: grid;
  gap: 10px;
}

.feedback-section,
.task-debt-summary {
  margin: 10px 12px;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.feedback-action-group,
.feedback-agent-section,
.task-debt-summary,
.notification-item {
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.feedback-action-group:hover,
.feedback-agent-section:hover,
.task-debt-summary:hover {
  border-color: rgba(59, 130, 246, 0.26);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.12);
  transform: translateY(-1px);
}

.feedback-action-group-primary {
  border-left: 3px solid #2563eb;
}

.feedback-action-group-task {
  border-left: 3px solid #d97706;
}

.feedback-action-group-agent {
  border-left: 3px solid #0f766e;
}

.feedback-action-group-knowledge {
  border-left: 3px solid #7c3aed;
}

.feedback-section-heading,
.task-debt-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.feedback-section-title {
  font-size: 12px;
  font-weight: 800;
  color: #334155;
}

.feedback-section-title-alert {
  margin-bottom: 0;
  color: #9f1239;
}

.feedback-section-summary,
.task-debt-caption {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  color: #64748b;
}

.feedback-section-count {
  flex: none;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 12px;
  font-weight: 800;
}

.feedback-load-section {
  margin: 10px 12px;
  padding: 10px;
  display: grid;
  gap: 8px;
  border: 1px solid rgba(251, 113, 133, 0.28);
  border-radius: 8px;
  background: rgba(255, 241, 242, 0.78);
  box-shadow: 0 10px 28px rgba(159, 18, 57, 0.08);
}

.feedback-loading-section {
  margin: 10px 12px;
  min-height: 42px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid rgba(59, 130, 246, 0.22);
  border-radius: 8px;
  background: rgba(239, 246, 255, 0.78);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
}

.feedback-loading-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #3b82f6;
  box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.36);
  animation: feedback-loading-pulse 1.2s ease-out infinite;
}

@keyframes feedback-loading-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.36);
  }
  100% {
    box-shadow: 0 0 0 9px rgba(59, 130, 246, 0);
  }
}

.feedback-load-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid rgba(248, 113, 113, 0.36);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.74);
  color: #991b1b;
}

.feedback-load-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.feedback-load-row-stale {
  border-color: rgba(217, 119, 6, 0.32);
  background: rgba(255, 251, 235, 0.8);
  color: #92400e;
}

.feedback-load-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.feedback-load-title {
  font-size: 12px;
  font-weight: 800;
}

.feedback-load-message,
.feedback-load-detail {
  font-size: 12px;
  line-height: 1.35;
}

.feedback-load-detail {
  color: #6b7280;
}

.feedback-load-retry,
.feedback-link,
.notification-mark-read {
  flex: none;
  min-height: 28px;
  border: 1px solid rgba(37, 99, 235, 0.24);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.82);
  color: #1d4ed8;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 9px;
  font-size: 12px;
  font-weight: 700;
  transition: background 0.14s ease, border-color 0.14s ease, color 0.14s ease, box-shadow 0.14s ease;
}

.feedback-load-retry {
  color: inherit;
  border-color: currentColor;
}

.feedback-load-retry.all {
  justify-self: end;
}

.feedback-load-retry:hover,
.feedback-link:hover,
.notification-mark-read:hover {
  border-color: rgba(37, 99, 235, 0.42);
  background: #eff6ff;
  color: #1e40af;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.12);
}

.feedback-load-retry:focus-visible,
.feedback-link:focus-visible,
.feedback-secondary-link:focus-visible,
.notification-mark-read:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.45);
  outline-offset: 2px;
}

.notification-list-title {
  margin: 12px 16px 4px;
}

.feedback-action-row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0 9px 12px;
}

.feedback-action-row::before {
  content: '';
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 999px;
  background: #60a5fa;
}

.feedback-action-row.urgent::before {
  background: #ef4444;
}

.feedback-action-row.warning::before {
  background: #f59e0b;
}

.feedback-action-row.success::before {
  background: #22c55e;
}

.feedback-action-row + .feedback-action-row {
  border-top: 1px solid rgba(226, 232, 240, 0.82);
}

.feedback-action-row.urgent .feedback-action-title {
  color: #b42318;
}

.feedback-action-row.warning .feedback-action-title {
  color: #b45309;
}

.feedback-action-row.success .feedback-action-title {
  color: #166534;
}

.feedback-action-body {
  flex: 1;
  min-width: 0;
}

.feedback-action-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.feedback-action-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feedback-action-copy {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
}

.feedback-secondary-actions {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-secondary-link {
  border: none;
  border-radius: 5px;
  padding: 2px 4px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
}

.feedback-secondary-link:hover {
  background: rgba(15, 23, 42, 0.05);
  color: #0f766e;
}

.feedback-link.inline {
  margin-top: 0;
}

.task-debt-summary {
  border-color: rgba(217, 119, 6, 0.26);
  background: rgba(255, 251, 235, 0.82);
}

.task-debt-summary-clean {
  border-color: rgba(34, 197, 94, 0.24);
  background: rgba(240, 253, 244, 0.84);
}

.task-debt-title {
  font-size: 13px;
  font-weight: 800;
  color: #1f2937;
}

.task-debt-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  font-size: 12px;
  color: var(--text-secondary);
}

.task-debt-metrics span {
  min-height: 24px;
  padding: 3px 8px;
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.task-debt-hint {
  margin-top: 8px;
  padding: 7px 9px;
  border-radius: 7px;
  background: rgba(217, 119, 6, 0.1);
  font-size: 12px;
  line-height: 1.45;
  color: #92400e;
}

.workflow-list {
  margin-top: 9px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.workflow-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
  padding: 5px 8px;
  border-radius: 7px;
  background: rgba(241, 245, 249, 0.76);
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
  color: #0f766e;
  font-weight: 800;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  margin: 0 12px;
  padding: 10px 4px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.82);
}

.notification-item:hover {
  background: rgba(241, 245, 249, 0.76);
}

.notification-item:last-child {
  border-bottom: none;
}

.notification-item-unread {
  margin-top: 2px;
  border-radius: 8px;
  background: rgba(239, 246, 255, 0.88);
  box-shadow: inset 3px 0 0 #3b82f6;
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
  font-weight: 800;
}

.notification-tag {
  flex-shrink: 0;
}

.notification-time {
  font-size: 12px;
  color: #94a3b8;
}

.notification-actions {
  flex-shrink: 0;
  margin-left: 12px;
  padding-top: 2px;
}

.notification-mark-read {
  min-height: 24px;
  padding: 0 8px;
}

.notification-read-label {
  font-size: 12px;
  color: var(--text-placeholder);
  white-space: nowrap;
}

.notification-empty {
  margin: 12px;
  padding: 26px 18px;
  text-align: center;
  border: 1px dashed rgba(148, 163, 184, 0.34);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.62);
}

.notification-empty-mark {
  width: 34px;
  height: 34px;
  margin: 0 auto 10px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
  font-weight: 800;
}

.empty-title {
  font-size: 14px;
  font-weight: 800;
  color: var(--text-primary);
}

.empty-copy {
  margin: 6px auto 0;
  max-width: 260px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.notification-panel-footer {
  margin: 6px 12px 0;
  padding: 8px 0 2px;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
  text-align: center;
}
</style>
