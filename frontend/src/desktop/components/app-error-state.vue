<template>
  <div class="app-error-state" :class="variantClass">
    <el-icon :size="iconSize" color="#f56c6c"><WarningFilled /></el-icon>
    <p class="app-error-state_message">{{ message || '系统开小差了' }}</p>
    <p v-if="description" class="app-error-state_description">{{ description }}</p>
    <div v-if="retryable || $slots.action" class="app-error-state_actions">
      <slot name="action">
        <el-button type="primary" size="small" @click="$emit('retry')">重新加载</el-button>
        <el-button size="small" @click="$emit('back')">返回首页</el-button>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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

const emit = defineEmits<{
  retry: []
  back: []
}>()

const variantClass = computed(() => `app-error-state--${props.variant}`)
</script>

<style scoped>
.app-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 12px;
}
.app-error-state--full {
  min-height: 260px;
  padding: 60px 20px;
}
.app-error-state--card {
  min-height: 200px;
  padding: 40px 20px;
  background: #fff5f5;
  border-radius: 8px;
}
.app-error-state--inline {
  padding: 20px;
}
.app-error-state_message {
  margin: 0;
  font-size: 14px;
  color: #606266;
}
.app-error-state_description {
  margin: 0;
  font-size: 12px;
  color: #909399;
}
.app-error-state_actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
</style>
