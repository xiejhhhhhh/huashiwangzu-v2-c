import { onUnmounted, watch, type Ref } from 'vue'
import { API_BASE_URL } from '@/shared/api'
import type { 知识库任务条目 } from '@/shared/api/types'

type 实时动态项 = { 时间: string; 文件ID: number; 文件名: string; 状态: string; 当前步骤: string; 百分比: number }
type 推送快照 = { 任务列表: 知识库任务条目[]; 实时动态: 实时动态项[] }

export function use任务轮询(
  激活标签: Ref<string>,
  更新快照: (数据: 推送快照) => void,
) {
  let sse: EventSource | null = null
  let 重连定时器: ReturnType<typeof setTimeout> | null = null
  let 已销毁 = false

  function 断开() {
    if (重连定时器) { clearTimeout(重连定时器); 重连定时器 = null }
    if (sse) { sse.close(); sse = null }
  }

  function 连接() {
    if (已销毁 || 激活标签.value !== '任务进度') return
    断开()
    sse = new EventSource(`${API_BASE_URL}/knowledge/tasks/stream`)
    sse.onmessage = (e) => {
      try {
        更新快照(JSON.parse(e.data) as 推送快照)
      } catch { /* ignore parse errors */ }
    }
    sse.onerror = () => {
      断开()
      if (!已销毁 && 激活标签.value === '任务进度') 重连定时器 = setTimeout(连接, 1500)
    }
  }

  watch(激活标签, 标签 => {
    if (标签 === '任务进度') 连接()
    else 断开()
  }, { immediate: true })

  onUnmounted(() => { 已销毁 = true; 断开() })
}
