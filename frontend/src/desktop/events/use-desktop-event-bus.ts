import { onUnmounted } from 'vue'
import emitter from './index'
import type { DesktopEventTypes } from './event-types'

export function use桌面事件总线() {
  const 监听器列表: Array<{ event: keyof DesktopEventTypes; handler: any }> = []

  function on<T extends keyof DesktopEventTypes>(event: T, handler: (data: DesktopEventTypes[T]) => void) {
    emitter.on(event, handler)
    监听器列表.push({ event, handler })
  }

  function off<T extends keyof DesktopEventTypes>(event: T, handler: (data: DesktopEventTypes[T]) => void) {
    emitter.off(event, handler)
    const index = 监听器列表.findIndex(item => item.event === event && item.handler === handler)
    if (index > -1) 监听器列表.splice(index, 1)
  }

  function emit<T extends keyof DesktopEventTypes>(event: T, data: DesktopEventTypes[T]) {
    emitter.emit(event, data)
  }

  onUnmounted(() => {
    监听器列表.forEach(({ event, handler }) => {
      emitter.off(event, handler)
    })
  })

  return { on, off, emit }
}
