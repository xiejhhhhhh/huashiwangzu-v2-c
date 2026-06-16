<template>
  <div class="通用状态" :class="[类型]">
    <div v-if="状态 === '加载中'" class="状态内容">
      <el-icon class="is-loading" :size="图标大小"><Loading /></el-icon>
      <p v-if="消息" class="消息">{{ 消息 }}</p>
    </div>
    <div v-else-if="状态 === '错误'" class="状态内容">
      <el-icon :size="图标大小" color="var(--danger-color, #f56c6c)"><WarningFilled /></el-icon>
      <p class="消息">{{ 消息 || '系统开小差了' }}</p>
      <el-button v-if="可重试" type="primary" size="small" @click="emit('重试')">重试</el-button>
    </div>
    <div v-else-if="状态 === '空'" class="状态内容">
      <el-icon :size="图标大小" color="#c0c4cc"><component :is="空图标 || 'FolderOpened'" /></el-icon>
      <p class="消息">{{ 消息 || '暂无内容' }}</p>
      <slot name="引导" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loading, WarningFilled, FolderOpened } from '@element-plus/icons-vue'

withDefaults(defineProps<{
  状态: '加载中' | '错误' | '空' | '正常'
  类型?: 'full' | 'card' | 'inline'
  消息?: string
  图标大小?: number
  空图标?: any
  可重试?: boolean
}>(), {
  类型: 'full',
  图标大小: 48,
  可重试: true
})

const emit = defineEmits<{
  (e: '重试'): void
}>()
</script>

<style scoped>
.通用状态 { display: flex; align-items: center; justify-content: center; width: 100%; }
.full { min-height: 300px; padding: 40px; }
.card { min-height: 200px; padding: 20px; background: #fafafa; border-radius: 8px; }
.inline { padding: 12px; }
.状态内容 { display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; }
.消息 { margin: 0; font-size: 14px; color: #909399; line-height: 1.6; }
</style>
