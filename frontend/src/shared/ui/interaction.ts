import { ElMessage, ElMessageBox } from 'element-plus'
import type { ElMessageBoxOptions } from 'element-plus'

export async function confirmDialog(
  message: string,
  title = '确认',
  options?: Partial<ElMessageBoxOptions>
): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      ...options,
    })
    return true
  } catch {
    return false
  }
}

export function alertDialog(
  message: string,
  title = '提示',
  options?: Partial<ElMessageBoxOptions>
): void {
  ElMessageBox.alert(message, title, options)
}

export const toast = {
  success: (msg: string, duration = 3000) => ElMessage.success({ message: msg, duration }),
  warning: (msg: string, duration = 4000) => ElMessage.warning({ message: msg, duration }),
  error: (msg: string, duration = 5000) => ElMessage.error({ message: msg, duration }),
  info: (msg: string, duration = 3000) => ElMessage.info({ message: msg, duration }),
}
