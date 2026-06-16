import type { Directive } from 'vue'
import { checkPermissionAction } from '@/shared/composables/use-permission-action'

export const vPermission: Directive = {
  async mounted(el, binding) {
    if (typeof binding.value !== 'string') {
      console.warn('[v-权限] 指令值必须为 action 字符串')
      return
    }
    const 有权限 = await checkPermissionAction(binding.value)
    if (!有权限) {
      el.parentNode?.removeChild(el)
    }
  },
}
