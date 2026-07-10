<template>
  <span class="workflow-status-badge" :class="`tone-${statusInfo.tone}`">
    {{ statusInfo.label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: string | null | undefined
}>()

interface StatusInfo {
  label: string
  tone: string
}

const STATUS_LABELS: Record<string, StatusInfo> = {
  waiting: { label: '等待中', tone: 'waiting' },
  processing: { label: '处理中', tone: 'processing' },
  needs_confirmation: { label: '需要确认', tone: 'confirmation' },
  completed: { label: '已完成', tone: 'completed' },
  failed: { label: '失败', tone: 'failed' },
  partial: { label: '部分完成', tone: 'partial' },
  cancelled: { label: '已取消', tone: 'neutral' },
  manual_required: { label: '需要人工处理', tone: 'confirmation' },
  pending: { label: '待处理', tone: 'waiting' },
  running: { label: '运行中', tone: 'processing' },
  paused: { label: '已暂停', tone: 'confirmation' },
  skipped: { label: '已跳过', tone: 'partial' },
  pass: { label: '通过', tone: 'completed' },
  fail: { label: '失败', tone: 'failed' },
  debt: { label: '有债务', tone: 'partial' },
  not_applicable: { label: '不适用', tone: 'neutral' },
  planned: { label: '已计划', tone: 'waiting' },
  waiting_approval: { label: '待确认', tone: 'confirmation' },
  interrupted: { label: '已中断', tone: 'partial' },
  blocked: { label: '已阻断', tone: 'failed' },
  rejected: { label: '已拒绝', tone: 'failed' },
}

const statusInfo = computed<StatusInfo>(() => {
  const status = props.status || 'waiting'
  return STATUS_LABELS[status] ?? { label: status, tone: 'neutral' }
})
</script>

<style scoped>
.workflow-status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid transparent;
  border-radius: var(--ag-radius-sm);
  font-size: var(--ag-font-size-xs);
  font-weight: 600;
  line-height: var(--ag-line-height-tight);
  white-space: nowrap;
}
.tone-waiting { color: #5f6b7a; background: #eef1f4; border-color: #dfe4ea; }
.tone-processing { color: #006d8a; background: #e8f4f8; border-color: #c8e6ef; }
.tone-confirmation { color: #8a5b00; background: #fff5d6; border-color: #f2d58a; }
.tone-completed { color: #24753a; background: #e6f5eb; border-color: #c5e8d0; }
.tone-failed { color: #b42318; background: #fff0ee; border-color: #fac5bf; }
.tone-partial { color: #8a5b00; background: #fff2e0; border-color: #edc58a; }
.tone-neutral { color: #5e5e5e; background: #f2f3f5; border-color: #dedede; }
</style>
