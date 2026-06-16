import { componentKeyMap as 生成映射 } from './component-key-map.generated'

// 旧数据库中文 entry_component_key → 组件加载器映射（V1→V2 兼容层）
// 新应用请直接在 component-key-map.generated.ts 中添加
const 旧键兼容映射: Record<string, string> = {
  '应用/agent/入口.vue': 'ai-assistant/index.vue',
  '应用/dashboard/入口.vue': '',
  '应用/desktop/入口.vue': '',
  '应用/knowledge/入口.vue': '',
  '应用/recycle/入口.vue': '',
  '应用/settings/入口.vue': '',
  '应用/tasks/入口.vue': '',
}

export const componentKeyMap: Record<string, () => Promise<{ default: any }>> = {
  ...生成映射,
}

// 将旧中文 key 也挂到 componentKeyMap 上，映射到对应的 English key 的加载器
for (const [旧键, 新键] of Object.entries(旧键兼容映射)) {
  if (新键 && 生成映射[新键]) {
    componentKeyMap[旧键] = 生成映射[新键]
  }
}
