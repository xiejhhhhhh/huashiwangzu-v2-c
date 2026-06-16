import { ref, watch, type Ref } from 'vue'
import { 桌面状态仓库, readAppState, 更新应用状态 } from './desktop-state-store'

export function use应用状态快照<T>(应用标识: string, 状态名: string, 默认值: T, 校验?: (值: T) => boolean): Ref<T> {
  const 状态 = ref<T>(默认值) as Ref<T>
  let 已载入 = false

  function 读取() {
    已载入 = false
    const 值 = readAppState(应用标识, 状态名, 默认值)
    if (!校验 || 校验(值)) 状态.value = 值
    已载入 = true
  }

  watch(桌面状态仓库.已加载, 已就绪 => { if (已就绪) 读取() }, { immediate: true })
  watch(状态, 值 => {
    if (!已载入) return
    更新应用状态(应用标识, 状态名, 值)
  }, { deep: true })

  return 状态
}
