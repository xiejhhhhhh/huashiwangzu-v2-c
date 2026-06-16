<template>
  <div class="加载状态提示" :class="[类型]">
    <el-icon class="旋转" :size="图标大小" color="#409eff"><Loading /></el-icon>
    <p v-if="消息" class="消息">{{ 消息 }}</p>
    <p v-if="说明" class="说明">{{ 说明 }}</p>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

withDefaults(defineProps<{
  类型?: 'full' | 'card' | 'inline'
  消息?: string
  说明?: string
  图标大小?: number
}>(), {
  类型: 'full',
  消息: '加载中，请稍候...',
  图标大小: 48,
})
</script>

<style scoped>
.加载状态提示 { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 12px; }
.full { min-height: 300px; padding: 60px 20px; }
.card { min-height: 200px; padding: 40px 20px; background: #fafafa; border-radius: 8px; }
.inline { padding: 20px; }
.旋转 { animation: 转圈 1s linear infinite; }
@keyframes 转圈 { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.消息 { margin: 0; font-size: 14px; color: #606266; }
.description { margin: 0; font-size: 12px; color: #c0c4cc; }
</style>
