<template>
  <div class="system-status-panel">
    <div v-if="loading" class="status-loading">加载系统状态中...</div>
    <div v-else-if="errorMessage" class="status-error">{{ errorMessage }}</div>
    <template v-else>
      <div v-if="!props.showDetails && !allHealthy" class="status-warning-bar">
        ⚠️ 系统部分服务异常，请联系管理员
      </div>
      <div v-if="props.showDetails" class="status-detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item v-for="(value, key) in systemStatus" :key="key" :label="key">
            <el-tag :type="value.status ? 'success' : 'danger'" size="small">
              {{ value.status ? '正常' : '异常' }}
            </el-tag>
            <span class="status-message">{{ value.message }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/shared/api'
import type { ApiResponse, SystemStatus, SystemStatusEntry } from '@/shared/api/types'

const props = withDefaults(defineProps<{ showDetails?: boolean }>(), { showDetails: false })

const systemStatus = ref<SystemStatus | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const allHealthy = computed(() => {
  if (!systemStatus.value) return true
  return Object.values(systemStatus.value).every((value: SystemStatusEntry) => value.status)
})

async function loadStatus() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await api.get<unknown, ApiResponse<SystemStatus>>('/system/status')
    if (response.success) {
      systemStatus.value = response.data || null
    } else {
      errorMessage.value = response.error || '加载失败'
    }
  } catch (error: unknown) {
    errorMessage.value = (error as { error?: string })?.error || '系统状态加载失败'
  } finally {
    loading.value = false
  }
}

defineExpose({ loadStatus })
onMounted(() => { loadStatus() })
</script>

<style scoped>
.system-status-panel { margin-bottom: 12px; }
.status-loading { color: var(--text-muted); padding: 8px 0; font-size: 14px; }
.status-error { color: var(--el-color-danger); padding: 8px 0; }
.status-warning-bar { background: var(--el-color-warning-light-9); color: var(--el-color-warning); padding: 8px 16px; border-radius: 4px; font-size: 14px; margin-bottom: 8px; }
.status-message { margin-left: 8px; font-size: 13px; color: var(--text-secondary); }
</style>
