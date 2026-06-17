<template>
  <div class="error-state" :class="[props.variant]">
    <el-icon :size="props.iconSize" color="#f56c6c"><WarningFilled /></el-icon>
    <p class="error-message">{{ props.message || '系统开小差了' }}</p>
    <p v-if="props.description" class="error-description">{{ props.description }}</p>
    <div v-if="props.retryable" class="error-actions">
      <el-button type="primary" size="small" @click="$emit('retry')">重新加载</el-button>
      <el-button size="small" @click="$emit('back')">返回首页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  variant?: 'full' | 'card' | 'inline'
  message?: string
  description?: string
  iconSize?: number
  retryable?: boolean
}>(), {
  variant: 'full',
  iconSize: 48,
  retryable: true,
})

defineEmits<{
  retry: []
  back: []
}>()
</script>

<style scoped>
.error-state { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 12px; }
.full { min-height: 300px; padding: 60px 20px; }
.card { min-height: 200px; padding: 40px 20px; background: #fff5f5; border-radius: 8px; }
.inline { padding: 20px; }
.error-message { margin: 0; font-size: 14px; color: #606266; }
.error-description { margin: 0; font-size: 12px; color: #909399; }
.error-actions { display: flex; gap: 12px; margin-top: 8px; }
</style>
