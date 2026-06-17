import type { Directive } from 'vue'
import { checkPermissionAction } from '@/shared/composables/use-permission-action'

export const vPermission: Directive = {
  async mounted(el, binding) {
    if (typeof binding.value !== 'string') {
      console.warn('[v-permission] directive value must be an action string')
      return
    }
    const hasPermission = await checkPermissionAction(binding.value)
    if (!hasPermission) {
      el.parentNode?.removeChild(el)
    }
  },
}
