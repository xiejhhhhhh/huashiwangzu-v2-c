<template>
  <div class="app-empty-state" :class="variantClass">
    <el-icon :size="iconSize" color="#c0c4cc">
      <component :is="iconComponent" />
    </el-icon>
    <p class="app-empty-state_message">{{ message || '暂无内容' }}</p>
    <p v-if="description" class="app-empty-state_description">{{ description }}</p>
    <div v-if="$slots.action" class="app-empty-state_action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FolderOpened, Search, ChatDotRound, Document, DataBoard } from '@element-plus/icons-vue'

const iconMap: Record<string, any> = {
  folder: FolderOpened,
  search: Search,
  chat: ChatDotRound,
  document: Document,
  data: DataBoard,
}

const props = withDefaults(defineProps<{
  variant?: 'full' | 'card' | 'inline'
  message?: string
  description?: string
  icon?: string
  iconSize?: number
}>(), {
  variant: 'full',
  icon: 'folder',
  iconSize: 48,
})

const variantClass = computed(() => `app-empty-state--${props.variant}`)

const iconComponent = computed(() => iconMap[props.icon] || FolderOpened)
</script>

<style scoped>
.app-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #909399;
  gap: 8px;
}
.app-empty-state--full {
  min-height: 260px;
  padding: 60px 20px;
}
.app-empty-state--card {
  min-height: 200px;
  padding: 40px 20px;
  background: #fafafa;
  border-radius: 8px;
}
.app-empty-state--inline {
  padding: 20px;
}
.app-empty-state_message {
  margin: 0;
  font-size: 14px;
  color: #909399;
}
.app-empty-state_description {
  margin: 0;
  font-size: 12px;
  color: #c0c4cc;
}
.app-empty-state_action {
  margin-top: 4px;
}
</style>
