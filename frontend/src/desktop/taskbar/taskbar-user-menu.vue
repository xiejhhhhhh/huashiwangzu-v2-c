<template>
  <el-dropdown trigger="click" placement="top-end" class="任务栏用户菜单-包装">
    <button class="任务栏用户菜单-按钮" type="button">
      <el-avatar :size="22">
        {{ 用户Store.用户信息?.displayName?.[0] || 用户Store.用户信息?.username?.[0] || '?' }}
      </el-avatar>
      <span class="任务栏用户菜单-名称">{{ 用户名 }}</span>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item @click="处理退出">退出登录</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/platform/stores/user'

const 用户Store = useUserStore()
const 用户名 = computed(() => 用户Store.用户信息?.displayName || 用户Store.用户信息?.username || '用户')

async function 处理退出() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '退出确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await 用户Store.登出()
    window.location.href = '/'
  } catch {
    // 用户取消，不做任何操作
  }
}
</script>

<style scoped>
.任务栏用户菜单-包装 {
  display: flex;
  align-items: center;
}
.任务栏用户菜单-按钮 {
  display: flex; align-items: center; gap: 6px;
  padding: 0 8px; height: 28px; border: none; background: transparent;
  color: #dbeafe; cursor: pointer; border-radius: 4px;
  opacity: .82; transition: background .12s, opacity .12s;
}
.任务栏用户菜单-按钮:hover { background: rgba(255,255,255,.08); opacity: 1; }
.任务栏用户菜单-名称 { font-size: 12px; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
