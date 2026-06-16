import { ref, watch, type Reactive } from 'vue'
import type { TaskbarItem, WindowState } from './window-types'
import { createDesktopWindowSnapshot } from './desktop-session-storage'
import { 保活保存桌面状态, 立即保存桌面状态, updateWindowSnapshot } from './desktop-state-store'

export function 创建WindowState同步(windows: Reactive<WindowState[]>) {
  const 任务栏项 = ref<TaskbarItem[]>([])
  function 立即保存() {
    updateWindowSnapshot(createDesktopWindowSnapshot(windows))
    void 立即保存桌面状态()
  }

  const 停止任务栏同步 = watch(() => windows.map((w: WindowState) => ({
    id: w.id, title: w.title, icon: w.icon,
    isActive: w.isActive, minimized: w.minimized,
  })), v => { 任务栏项.value = v }, { immediate: true, deep: true })

  const 停止会话同步 = watch(windows, () => {
    updateWindowSnapshot(createDesktopWindowSnapshot(windows))
  }, { deep: true })

  window.addEventListener('pagehide', 保活保存桌面状态)

  function 停止同步() {
    立即保存()
    停止任务栏同步()
    停止会话同步()
    window.removeEventListener('pagehide', 保活保存桌面状态)
  }

  return {
    任务栏项,
    立即保存,
    停止同步,
  }
}
