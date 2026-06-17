<template>
  <el-dropdown trigger="click" placement="top-end" class="taskbar-user-menu-wrapper">
    <button class="taskbar-user-menu-button" type="button">
      <el-avatar :size="22">
        {{ userStore.userInfo?.displayName?.[0] || userStore.userInfo?.username?.[0] || '?' }}
      </el-avatar>
      <span class="taskbar-user-menu-name">{{ userName }}</span>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/platform/stores/user'

const userStore = useUserStore()
const userName = computed(() => userStore.userInfo?.displayName || userStore.userInfo?.username || '用户')

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '退出确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await userStore.logout()
    window.location.href = '/'
  } catch {
    // 用户取消，不做任何操作
  }
}
</script>

<style scoped>
.taskbar-user-menu-wrapper {
  display: flex;
  align-items: center;
}
.taskbar-user-menu-button {
  display: flex; align-items: center; gap: 6px;
  padding: 0 8px; height: 28px; border: none; background: transparent;
  color: #dbeafe; cursor: pointer; border-radius: 4px;
  opacity: .82; transition: background .12s, opacity .12s;
}
.taskbar-user-menu-button:hover { background: rgba(255,255,255,.08); opacity: 1; }
.taskbar-user-menu-name { font-size: 12px; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
