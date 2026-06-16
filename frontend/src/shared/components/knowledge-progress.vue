<template>
  <div class="知识进度">
    <div class="进度行">
      <el-progress :percentage="进度?.百分比 ?? 0" :stroke-width="8" :status="状态" class="进度条" />
      <b class="进度值">{{ 进度?.百分比 ?? 0 }}%</b>
    </div>
    <div v-if="!简洁" class="阶段条">
      <span v-for="项 in 进度?.阶段列表 || []" :key="项.名称" :class="`阶段-${项.状态}`">{{ 项.名称 }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { 知识进度 } from '@/shared/api/types'

const props = defineProps<{ 进度?: 知识进度; 简洁?: boolean }>()
const 状态 = computed(() => {
  const 列表 = props.进度?.阶段列表 || []
  if (列表.some(项 => 项.状态 === '失败')) return 'exception'
  if ((props.进度?.百分比 || 0) >= 100) return 'success'
  return undefined
})
</script>

<style scoped>
.知识进度 { min-width: 180px; }
.进度行 { display:flex; align-items:center; gap:10px; }
.进度条 { flex:1; min-width:0; }
.进度值 { font-size:13px; color:#0f172a; white-space:nowrap; flex-shrink:0; }
.阶段条 { margin-top:6px; display:flex; flex-wrap:wrap; gap:4px; }
.阶段条 span { font-size:11px; line-height:1; padding:4px 6px; border-radius:7px; background:#f1f5f9; color:#64748b; }
.阶段条 .阶段-完成 { color:#047857; background:#ecfdf5; }
.阶段条 .阶段-执行中 { color:#1d4ed8; background:#eff6ff; }
.阶段条 .阶段-失败 { color:#b91c1c; background:#fef2f2; }
</style>
