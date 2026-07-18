import {
  desktopMessage,
  showAlert,
  showConfirm,
  showToast,
  type OperationToast,
} from '@/desktop/feedback/desktop-feedback'

/**
 * Business apps should use this instead of Element Plus ElMessage/ElMessageBox.
 * Keeps OS-level feedback on the desktop kit channel.
 */
export function useAppFeedback() {
  return {
    message: desktopMessage,
    toast: showToast,
    alert: showAlert,
    confirm: showConfirm,
    success: (message: string) => desktopMessage.success(message),
    info: (message: string) => desktopMessage.info(message),
    warning: (message: string) => desktopMessage.warning(message),
    error: (message: string) => desktopMessage.error(message),
    notify(
      message: string,
      type: OperationToast['type'] = 'info',
      duration?: number,
    ) {
      showToast(message, { type, duration })
    },
  }
}

export type AppFeedback = ReturnType<typeof useAppFeedback>
