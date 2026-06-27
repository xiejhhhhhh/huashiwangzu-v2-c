<template>
  <div class="taskbar-notifications-wrapper" ref="notificationContainer">
    <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="taskbar-notifications-badge">
      <button class="taskbar-notifications-button" type="button" title="通知" @click.stop="toggleNotificationPanel">
        <el-icon :size="18"><Bell /></el-icon>
      </button>
    </el-badge>
    <div v-if="showNotificationPanel" class="taskbar-notifications-panel" @click.stop>
      <NotifyPanel
        :show="showNotificationPanel"
        :items="notificationList"
        @mark-read="markRead"
        @mark-all-read="markAllRead"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bell } from '@element-plus/icons-vue'
import { useNotifications } from '@/shared/composables/use-notifications'
import NotifyPanel from '@/shared/components/notification-panel.vue'

const { unreadCount, notificationList, showNotificationPanel, toggleNotificationPanel, markRead, markAllRead } = useNotifications()
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
