import { ref, onMounted, onUnmounted } from 'vue'
import api from '@/shared/api'
import type { 公告条目 } from '@/shared/api/types'

async function 获取通知列表() {
  const res = await api.get('/notifications')
  return res.data
}
async function 获取未读数() {
  const res = await api.get('/notifications/unread-count')
  return res.data
}
async function 标记已读请求(id: number) {
  const res = await api.post(`/notifications/${id}/read`)
  return res.data
}
async function 全部已读请求() {
  const res = await api.post('/notifications/read-all')
  return res.data
}

export function use通知(容器选择器 = '.任务栏通知-包装') {
  const 未读数 = ref(0)
  const 通知列表 = ref<公告条目[]>([])
  const 显示通知面板 = ref(false)

  async function 加载未读数() {
    try {
      const res = await 获取未读数()
      if (res.success) {
        未读数.value = res.data.未读数
      }
    } catch {
      未读数.value = 0
    }
  }

  async function 加载通知列表() {
    try {
      const res = await 获取通知列表()
      if (res.success) {
        通知列表.value = res.data.列表
      }
    } catch {
      通知列表.value = []
    }
  }

  async function 标记已读(id: number) {
    try {
      const res = await 标记已读请求(id)
      if (res.success) {
        const 项 = 通知列表.value.find((n) => n.id === id)
        if (项) 项.是否已读 = true
        未读数.value = Math.max(0, 未读数.value - 1)
      }
    } catch {
      // 静默失败
    }
  }

  async function 全部已读() {
    try {
      const res = await 全部已读请求()
      if (res.success) {
        通知列表.value.forEach((n) => { n.是否已读 = true })
        未读数.value = 0
      }
    } catch {
      // 静默失败
    }
  }

  function 切换通知面板() {
    显示通知面板.value = !显示通知面板.value
    if (显示通知面板.value) {
      加载通知列表()
    }
  }

  function 点击外部关闭(e: MouseEvent) {
    const 目标 = e.target as HTMLElement
    if (!目标.closest(容器选择器)) {
      显示通知面板.value = false
    }
  }

  onMounted(() => {
    加载未读数()
    document.addEventListener('click', 点击外部关闭)
  })

  onUnmounted(() => {
    document.removeEventListener('click', 点击外部关闭)
  })

  return {
    未读数, 通知列表, 显示通知面板,
    切换通知面板, 加载未读数, 标记已读, 全部已读,
  }
}
