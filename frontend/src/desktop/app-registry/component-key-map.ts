import type { Component } from 'vue'
import { platformComponentKeyMap } from './platform-component-key-map'
import { componentKeyMap as generatedMap } from './component-key-map.generated'

export const componentKeyMap: Record<string, () => Promise<{ default: Component }>> = {
  ...platformComponentKeyMap,
  ...generatedMap,
}
