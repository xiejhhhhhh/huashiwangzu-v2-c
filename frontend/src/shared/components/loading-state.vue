<template>
  <div class="loading-state" :class="[props.variant]">
    <el-icon class="loading-spin" :size="props.iconSize" color="#409eff"><Loading /></el-icon>
    <p v-if="props.message" class="loading-message">{{ props.message }}</p>
    <p v-if="props.description" class="loading-description">{{ props.description }}</p>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  variant?: 'full' | 'card' | 'inline'
  message?: string
  description?: string
  iconSize?: number
}>(), {
  variant: 'full',
  message: '加载中，请稍候...',
  iconSize: 48,
})
</script>

<style scoped>
.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 12px; }
.full { min-height: 300px; padding: 60px 20px; }
.card { min-height: 200px; padding: 40px 20px; background: #fafafa; border-radius: 8px; }
.inline { padding: 20px; }
.loading-spin { animation: loading-spin 1s linear infinite; }
@keyframes loading-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.loading-message { margin: 0; font-size: 14px; color: #606266; }
.loading-description { margin: 0; font-size: 12px; color: #c0c4cc; }
</style>
