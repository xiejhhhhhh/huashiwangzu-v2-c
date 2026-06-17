import api from './index'
import type { ApiResponse } from './types'

/** Desktop app item type used by frontend components */
export interface DesktopAppItem {
  app_id: string
  name: string
  icon: string
  description: string
  entry_component_key: string
  default_width: number
  default_height: number
  singleton?: boolean
  category?: string
  window_type?: string
  min_width?: number
  min_height?: number
  allow_multiple?: boolean
  permissions?: string[]
  show_on_desktop?: boolean
  show_in_tray?: boolean
  show_in_launcher?: boolean
  show_in_sidebar?: boolean
  supported_formats?: string[]
  editable_formats?: string[]
  creatable_formats?: Array<{ extension: string; label: string; mime_type?: string }>
  sort_order?: number
  capabilities?: {
    canReceiveFile: boolean
    canSendNotification: boolean
    canRunBackground: boolean
    canBeCalledByOther: boolean
  }
  public_actions?: Array<{
    action: string
    description: string
    paramSchema: Record<string, unknown>
  }>
  enabled?: boolean
}

export function fetchDesktopApps() {
  return api.get<unknown, ApiResponse<DesktopAppItem[]>>('/desktop/apps')
}

export function getDesktopAppDetail(appKey: string) {
  return api.get<unknown, ApiResponse<DesktopAppItem>>(`/desktop/apps/${appKey}`)
}
