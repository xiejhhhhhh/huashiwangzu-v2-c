import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { use桌面事件总线 } from '@/desktop/events/use-desktop-event-bus'
import { 收集拖放文件, 上传拖放文件 } from '@/shared/upload/directory-upload'

export function useDesktopShellDropUpload() {
  const { emit } = use桌面事件总线()
  const 桌面拖放激活 = ref(false)

  function 是外部文件(e: DragEvent) {
    return Array.from(e.dataTransfer?.types || []).includes('Files')
  }

  function 桌面拖入(e: DragEvent) {
    if (!是外部文件(e)) return
    e.preventDefault()
    桌面拖放激活.value = true
  }

  function 桌面拖离(e: DragEvent) {
    if (!是外部文件(e)) return
    e.preventDefault()
    桌面拖放激活.value = false
  }

  async function 桌面放下(e: DragEvent) {
    if (!是外部文件(e)) return
    e.preventDefault()
    桌面拖放激活.value = false
    const 文件列表 = await 收集拖放文件(e.dataTransfer?.items || null)
    if (!文件列表.length) return
    const 结果 = await 上传拖放文件(文件列表, null)
    emit('refresh:file-list', { 文件夹id: 0 })
    if (结果.成功数 > 0) ElMessage.success(`已上传 ${结果.成功数} 个项目到桌面`)
    if (结果.失败数 > 0) ElMessage.warning(`${结果.失败数} 个项目上传失败`)
  }

  return { 桌面拖放激活, 桌面拖入, 桌面拖离, 桌面放下 }
}
