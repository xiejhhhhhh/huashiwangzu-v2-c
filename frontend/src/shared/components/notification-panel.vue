<template>
  <div v-if="show" class="notification-panel">
    <div class="notification-panel-header">
      <span class="notification-panel-title">公告通知</span>
    </div>
    <div v-if="items.length === 0" class="notification-empty">暂无公告</div>
    <div v-for="item in items" :key="item.id" class="notification-item" :class="{ 'notification-item-unread': !item.is_read }">
      <div class="notification-item-content">
        <div class="notification-title-row">
          <span class="notification-title" :class="{ 'notification-title-unread': !item.is_read }">{{ item.title }}</span>
          <el-tag :type="tagType(item.type)" size="small" class="notification-tag">{{ item.type }}</el-tag>
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

defineProps<{
 show: boolean
 items: NotificationItem[]
}>()

const emit = defineEmits<{
  'mark-read': [id: number]
  'mark-all-read': []
}>()

function tagType(type: string) {
  const typeMap: Record<string, string> = {
    '系统公告': 'danger',
    '维护通知': 'warning',
    '更新日志': 'primary',
    '普通通知': 'info',
  }
  return typeMap[type] || 'info'
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

.notification-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid #f5f5f5;
  transition: background 0.15s;
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

.notification-panel-footer {
  padding: 10px 16px;
  border-top: 1px solid #f0f0f0;
  text-align: center;
}
</style>
