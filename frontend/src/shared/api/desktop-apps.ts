import api from './index'
import type { 统一响应 } from './types'

/** Desktop app item type used by frontend components */
export interface DesktopAppItem {
  appKey: string
  appName: string
  icon: string
  description: string
  entryComponentKey: string
  defaultWidth: number
  defaultHeight: number
  singleton: boolean
  category?: string
  windowType?: string
  minWidth?: number
  minHeight?: number
  allowMultiple?: boolean
  allowedRoles?: string[]
  showOnDesktop?: boolean
  showInTray?: boolean
  showInLauncher?: boolean
  showInSidebar?: boolean
  supportedFileFormats?: string[]
  capabilities?: any
  publicActions?: any[]
  enabled?: boolean
}

export function fetchDesktopApps() {
  return api.get<unknown, 统一响应<DesktopAppItem[]>>('/desktop/apps')
}

export function getDesktopAppDetail(appKey: string) {
  return api.get<unknown, 统一响应<DesktopAppItem>>(`/desktop/apps/${appKey}`)
}
