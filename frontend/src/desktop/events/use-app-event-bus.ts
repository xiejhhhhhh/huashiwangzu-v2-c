import { onUnmounted } from 'vue'
import emitter from './index'
import type { DesktopEventTypes } from './event-types'

interface 监听器记录 {
  事件: string
  处理器: (载荷: unknown) => void
}

export function use应用事件总线() {
  const 监听器列表: 监听器记录[] = []

  function on<T extends keyof DesktopEventTypes>(事件: T, 处理器: (数据: DesktopEventTypes[T]) => void) {
    emitter.on(事件, 处理器 as never)
    监听器列表.push({ 事件: 事件 as string, 处理器: 处理器 as unknown as (载荷: unknown) => void })
  }

  function off<T extends keyof DesktopEventTypes>(事件: T, 处理器: (数据: DesktopEventTypes[T]) => void) {
    emitter.off(事件, 处理器 as never)
    const index = 监听器列表.findIndex(i => i.事件 === 事件 && i.处理器 === 处理器)
    if (index > -1) 监听器列表.splice(index, 1)
  }

  function emit<T extends keyof DesktopEventTypes>(事件: T, 数据: DesktopEventTypes[T]) {
    emitter.emit(事件, 数据)
  }

  function 只监听一次<T extends keyof DesktopEventTypes>(事件: T, 处理器: (数据: DesktopEventTypes[T]) => void) {
    const 包装函数 = (数据: DesktopEventTypes[T]) => {
      处理器(数据)
      off(事件, 包装函数)
    }
    on(事件, 包装函数)
  }

  onUnmounted(() => {
    监听器列表.forEach(({ 事件, 处理器 }) => {
      emitter.off(事件 as never, 处理器 as never)
    })
  })

  return { on, off, emit, 只监听一次 }
}
