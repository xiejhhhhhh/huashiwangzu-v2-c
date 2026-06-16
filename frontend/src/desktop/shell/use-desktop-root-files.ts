import { onMounted, onUnmounted, ref } from 'vue'
import { 获取文件列表请求 } from '@/shared/api/desktop'
import type { FileEntry } from '@/shared/api/types'
import { use桌面事件总线 } from '@/desktop/events/use-desktop-event-bus'
import { openFileByRecord } from '@/desktop/app-registry/app-opener'
import { 窗口管理器 } from '@/desktop/window-manager/window-manager'
import { 格式化文件displayName } from '@/shared/files/display-name'

function displayName(文件: FileEntry) {
  return 文件.是否为文件夹 ? String(文件.文件名 || '') : 格式化文件displayName(文件.文件名, 文件.格式)
}

export function useDesktopRootFiles() {
  const 桌面文件列表 = ref<FileEntry[]>([])
  const { on, off } = use桌面事件总线()

  async function loadDesktopFiles() {
    const 响应 = await 获取文件列表请求(0)
    if (响应.success) 桌面文件列表.value = 响应.data?.列表 || []
  }

  function onFileRefresh(d?: { 文件夹id?: number }) {
    if (d?.文件夹id === undefined || d.文件夹id === 0) void loadDesktopFiles()
  }

  function openDesktopEntry(文件: FileEntry) {
    if (文件.是否为文件夹 || !文件.格式) {
      窗口管理器.打开窗口('desktop')
      return
    }
    openFileByRecord({ fileId: 文件.id, fileName: displayName(文件), format: 文件.格式 })
  }

  onMounted(() => {
    void loadDesktopFiles()
    on('refresh:file-list', onFileRefresh)
    on('file:uploaded', onFileRefresh)
    on('file:created', onFileRefresh)
  })
  onUnmounted(() => {
    off('refresh:file-list', onFileRefresh)
    off('file:uploaded', onFileRefresh)
    off('file:created', onFileRefresh)
  })

  return { 桌面文件列表, openDesktopEntry }
}
