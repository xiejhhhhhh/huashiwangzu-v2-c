import { reactive } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'

const appRegistry = reactive<Record<string, AppRegistryEntry>>({})

export function setAppRegistry(appList: AppRegistryEntry[]) {
  for (const key of Object.keys(appRegistry)) {
    delete appRegistry[key]
  }
  for (const app of appList) {
    appRegistry[app.appKey] = app
  }
}

export function getAppRegistry(): Record<string, AppRegistryEntry> {
  return appRegistry
}

export function getApp(key: string): AppRegistryEntry | undefined {
  return appRegistry[key]
}
