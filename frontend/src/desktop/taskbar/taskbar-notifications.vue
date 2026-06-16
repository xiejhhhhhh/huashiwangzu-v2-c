<template>
  <div class="任务栏通知-包装" ref="通知容器">
    <el-badge :value="未读数" :hidden="未读数 === 0" class="任务栏通知-徽章">
      <button class="任务栏通知-按钮" type="button" title="通知" @click.stop="切换通知面板">
        <el-icon :size="18"><Bell /></el-icon>
      </button>
    </el-badge>
    <div v-if="显示通知面板" class="任务栏通知-面板" @click.stop>
      <NotifyPanel
        :显示="显示通知面板"
        :列表="通知列表"
        @标记已读="标记已读"
        @全部已读="全部已读"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bell } from '@element-plus/icons-vue'
import { use通知 } from '@/shared/composables/use-notifications'
import NotifyPanel from '@/shared/components/notification-panel.vue'

const { 未读数, 通知列表, 显示通知面板, 切换通知面板, 标记已读, 全部已读 } = use通知()
</script>

<style scoped>
.任务栏通知-包装 {
  position: relative;
  display: flex;
  align-items: center;
}
.任务栏通知-徽章 :deep(.el-badge__content) {
  font-size: 10px;
  height: 16px;
  line-height: 16px;
  padding: 0 5px;
  border: none;
}
.任务栏通知-按钮 {
  width: 28px; height: 28px; border: none; background: transparent;
  color: #dbeafe; cursor: pointer; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  opacity: .82; transition: background .12s, opacity .12s;
}
.任务栏通知-按钮:hover { background: rgba(255,255,255,.08); opacity: 1; }
.任务栏通知-面板 {
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
