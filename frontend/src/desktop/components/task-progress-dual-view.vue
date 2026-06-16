<template>
  <div>
    <CommonState v-if="!活跃任务.length && !实时动态.length" 状态="空" 消息="暂无待处理任务" />
    <template v-else>
      <el-table :data="活跃任务" class="知识表格" stripe>
        <el-table-column label="文件名" min-width="180" show-overflow-tooltip>
          <template #default="{ row }"><span class="文件名链接" @click="emit('openFile', row.文件ID)">{{ row.文件名 || `文件 ${row.文件ID}` }}</span></template>
        </el-table-column>
        <el-table-column label="进度" min-width="180">
          <template #default="{ row }"><KnowledgeProgress :进度="row.进度" 简洁 /></template>
        </el-table-column>
        <el-table-column prop="状态" label="状态" width="100">
          <template #default="{ row }"><el-tag :type="状态类型(row.状态)" size="small">{{ row.状态 }}</el-tag></template>
        </el-table-column>
      </el-table>
      <div v-if="实时动态.length" class="动态日志">
        <div class="日志标题">实时进度</div>
        <div class="日志列表">
          <div v-for="(项, i) in 实时动态" :key="i" class="日志行">
            <span class="日志时间">{{ 项.时间?.slice(11, 19) || '' }}</span>
            <span :class="['日志状态', `日志状态-${项.状态}`]">{{ 项.状态 === '待执行' ? '排队中' : '处理中' }}</span>
            <span class="日志文件">{{ 项.文件名 }}</span>
            <span class="日志步骤">{{ 项.当前步骤 }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { 知识库任务条目 } from '@/shared/api/types'
import KnowledgeProgress from '@/shared/components/knowledge-progress.vue'
import CommonState from '@/shared/components/common-state.vue'

const props = defineProps<{
  任务列表: 知识库任务条目[]
  实时动态: Array<{ 时间: string; 文件ID: number; 文件名: string; 状态: string; 当前步骤: string; 百分比: number }>
  状态类型: (状态: string) => string
}>()
const emit = defineEmits<{ openFile: [文件ID: number] }>()
const 活跃任务 = computed(() => props.任务列表.filter(t => t.状态 === '待执行' || t.状态 === '执行中'))
</script>

<style scoped>
.fileName链接 { color:#0f172a; cursor:pointer; font-weight:600; padding:2px 6px; border-radius:6px; transition:background .15s ease; display:inline-block; }
.fileName链接:hover { background:rgba(15,23,42,.06); }
.动态日志 { margin-top:14px; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; }
.日志标题 { padding:8px 12px; font-size:12px; font-weight:700; color:#475569; background:#f8fafc; border-bottom:1px solid #e2e8f0; }
.日志列表 { max-height:160px; overflow-y:auto; padding:4px 0; }
.日志行 { display:flex; align-items:center; gap:8px; padding:4px 12px; font-size:12px; font-family:monospace; }
.日志行:nth-child(even) { background:#f8fafc; }
.日志时间 { color:#94a3b8; flex-shrink:0; }
.日志状态 { font-size:11px; padding:1px 5px; border-radius:4px; flex-shrink:0; }
.日志状态-待执行 { background:#fef3c7; color:#d97706; }
.日志状态-执行中 { background:#dbeafe; color:#2563eb; }
.日志文件 { color:#0f172a; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; flex:1; }
.日志步骤 { color:#64748b; flex-shrink:0; }
</style>
