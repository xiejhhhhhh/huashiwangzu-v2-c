<template>
  <div v-if="显示" class="通知面板">
    <div class="通知面板头部">
      <span class="通知面板标题">公告通知</span>
    </div>
    <div v-if="列表.length === 0" class="通知空状态">暂无公告</div>
    <div v-for="项 in 列表" :key="项.id" class="通知项" :class="{ '通知项_未读': !项.是否已读 }">
      <div class="通知项内容">
        <div class="通知项标题行">
          <span class="通知项标题" :class="{ '通知项标题_未读': !项.是否已读 }">{{ 项.标题 }}</span>
          <el-tag :type="标签类型(项.类型)" size="small" class="通知项标签">{{ 项.类型 }}</el-tag>
        </div>
        <div class="通知项时间">{{ 项.发布时间 }}</div>
      </div>
      <div class="通知项操作">
        <span v-if="!项.是否已读" class="通知标记已读" @click.stop="处理标记已读(项.id)">标为已读</span>
        <span v-else class="通知已读标记">✓ 已读</span>
      </div>
    </div>
    <div v-if="列表.length > 0" class="通知面板底部">
      <el-button text size="small" @click="处理全部已读">全部已读</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { 公告条目 } from '@/shared/api/types'

defineProps<{
 显示: boolean
 列表: 公告条目[]
}>()

const emit = defineEmits<{
  标记已读: [id: number]
  全部已读: []
}>()

function 标签类型(类型: string) {
  const 映射: Record<string, string> = {
    '系统公告': 'danger',
    '维护通知': 'warning',
    '更新日志': 'primary',
    '普通通知': 'info',
  }
  return 映射[类型] || 'info'
}

function 处理标记已读(id: number) {
  emit('标记已读', id)
}

function 处理全部已读() {
  emit('全部已读')
}
</script>

<style scoped>
.通知面板头部 {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f0f0f0;
}

.通知面板标题 {
  font-size: 15px;
  font-weight: 600;
  color: var(--文字主色);
}

.通知项 {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  border-bottom: 1px solid #f5f5f5;
  transition: background 0.15s;
}

.通知项:hover {
  background: #f6f8fa;
}

.通知项:last-child {
  border-bottom: none;
}

.通知项_未读 {
  background: var(--主色浅);
}

.通知项内容 {
  flex: 1;
  min-width: 0;
}

.通知项标题行 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.通知项标题 {
  font-size: 14px;
  color: var(--文字主色);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.通知项标题_未读 {
  font-weight: 600;
}

.通知项标签 {
  flex-shrink: 0;
}

.通知项时间 {
  font-size: 12px;
  color: var(--文字占位);
}

.通知项操作 {
  flex-shrink: 0;
  margin-left: 12px;
  padding-top: 2px;
}

.通知标记已读 {
  font-size: 12px;
  color: var(--主色);
  cursor: pointer;
  white-space: nowrap;
}

.通知标记已读:hover {
  color: var(--主色深);
}

.通知已读标记 {
  font-size: 12px;
  color: var(--文字占位);
  white-space: nowrap;
}

.通知面板底部 {
  padding: 10px 16px;
  border-top: 1px solid #f0f0f0;
  text-align: center;
}
</style>
