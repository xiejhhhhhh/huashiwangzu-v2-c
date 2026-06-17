<template>
  <div class="main-layout">
    <!-- 在 V1.5 中：当路由为 /desktop 时，由桌面壳接管全屏布局，隐藏传统侧边栏与顶部栏 -->
    <div v-if="currentPath !== '/desktop'" class="layout-sidebar">
      <div class="layout-sidebar-title">华世王镞</div>
      <div class="layout-sidebar-menu">
        <el-menu :default-active="currentPath" router>
          <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
            <el-icon><component :is="getIconComponent(item.icon)" /></el-icon>
            <span>{{ item.name }}</span>
          </el-menu-item>
        </el-menu>
      </div>
    </div>

    <div class="main-content">
      <div v-if="currentPath !== '/desktop'" class="topbar">
        <div class="topbar-left">
          <div class="notification-button" @click="toggleNotificationPanel">
            <el-badge :value="unreadCount" :hidden="unreadCount <= 0" class="notification-badge">
              <el-icon :size="22"><Bell /></el-icon>
            </el-badge>
            <NoticePanel
              :show="showNotificationPanel"
              :items="notificationList"
              @mark-read="markRead"
              @mark-all-read="markAllRead"
            />
          </div>
        </div>
        <div class="topbar-right">
          <el-button class="feedback-button" type="primary" size="small" @click="showFeedbackDialog = true">
            问题反馈
          </el-button>
           <FeedbackSubmitDialog :show="showFeedbackDialog" @close="showFeedbackDialog = false" @submit-success="showFeedbackDialog = false" />
          <el-dropdown trigger="click" @command="handleDropdown">
            <span style="cursor: pointer; display: flex; align-items: center; gap: 8px;">
              <el-avatar :size="32" style="background: var(--primary-color);">
                {{ store.userInfo?.displayName?.charAt(0) || '?' }}
              </el-avatar>
              <span>{{ store.userInfo?.displayName || '用户' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="content-area">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Component } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, Bell } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/platform/stores/user'
import { usePermission } from '@/shared/composables/use-permission'
import NoticePanel from '@/shared/components/notification-panel.vue'
import FeedbackSubmitDialog from './feedback-submit-dialog.vue'
import { useNotifications } from '@/shared/composables/use-notifications'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import type { MenuItem } from '@/shared/api/types'

const showFeedbackDialog = ref(false)
const route = useRoute()
const store = useUserStore()
const currentPath = computed(() => route.path)
const { unreadCount, notificationList, showNotificationPanel, toggleNotificationPanel, markRead, markAllRead } = useNotifications('.notification-button')
const { canAccessMenu } = usePermission()

const allMenuItems: MenuItem[] = [
  { name: '桌面', path: '/desktop', icon: 'Files' },
]

const menuItems = computed(() => allMenuItems.filter(item => canAccessMenu(item)))

function getIconComponent(name: string) {
  return (ElementPlusIconsVue as Record<string, unknown>)[name] as Component
}

function handleDropdown(command: string) {
  if (command === 'logout') {
    ElMessageBox.confirm('确定退出登录？', '提示').then(() => {
      store.logout().finally(() => {
        window.location.replace('/')
      })
    }).catch(() => {})
  }
}
</script>
