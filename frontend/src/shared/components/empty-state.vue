<template>
  <div class="empty-state" :class="[props.variant]">
    <el-icon :size="props.iconSize" color="#c0c4cc"><component :is="iconComponent" /></el-icon>
    <p class="empty-message">{{ props.message || '暂时没有内容' }}</p>
    <p v-if="props.description" class="empty-description">{{ props.description }}</p>
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import { FolderOpened, Search, ChatDotRound, Document } from '@element-plus/icons-vue'

const iconMap: Record<string, Component> = {
  folder: FolderOpened,
  search: Search,
  chat: ChatDotRound,
  document: Document,
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

const iconComponent = computed(() => iconMap[props.icon] || FolderOpened)
</script>

<style scoped>
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #909399; gap: 8px; }
.full { min-height: 300px; padding: 60px 20px; }
.card { min-height: 200px; padding: 40px 20px; background: #fafafa; border-radius: 8px; }
.inline { padding: 20px; }
.empty-message { margin: 0; font-size: 14px; color: #909399; }
.empty-description { margin: 0; font-size: 12px; color: #c0c4cc; }
</style>
