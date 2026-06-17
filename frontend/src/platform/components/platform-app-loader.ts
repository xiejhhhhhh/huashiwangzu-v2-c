import { defineComponent, h } from 'vue'
import type { Component } from 'vue'
import PlatformAppPlaceholder from './platform-app-placeholder.vue'

export interface PlatformAppMeta {
  appKey: string
  appName: string
  routePrefix?: string
  status: string
  message: string
}

export type AppComponentLoader = () => Promise<{ default: Component }>

export function createPlatformAppLoader(meta: PlatformAppMeta): AppComponentLoader {
  return async () => ({
    default: defineComponent({
      name: `PlatformApp_${meta.appKey.replace(/-/g, '_')}`,
      setup() {
        return () => h(PlatformAppPlaceholder, meta)
      },
    }),
  })
}
