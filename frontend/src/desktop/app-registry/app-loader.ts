import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { fetchDesktopApps } from '@/shared/api/desktop-apps'
import type { DesktopAppItem } from '@/shared/api/desktop-apps'
import { componentKeyMap } from '@/desktop/app-registry/component-key-map'
import { setAppRegistry } from '@/desktop/app-registry/desktop-app-state'

/** 从 API 响应的 snake_case 字段中读取值，兼容 camelCase */
function 取值(对象: any, ...键们: string[]): any {
  for (const 键 of 键们) {
    if (对象[键] !== undefined) return 对象[键]
  }
  return undefined
}

function transformApiToEntry(app: DesktopAppItem): AppRegistryEntry {
  // API 返回 snake_case（如 entry_component_key），接口声明是 camelCase（如 entryComponentKey）
  const entryKey: string = 取值(app, 'entry_component_key', 'entryComponentKey') || ''
  const componentLoader = componentKeyMap[entryKey]
  return {
    appKey: 取值(app, 'app_id', 'appKey') || '',
    appName: 取值(app, 'name', 'appName') || '',
    icon: app.icon,
    description: app.description,
    entryComponent: componentLoader || (() => Promise.resolve({ default: null })),
    defaultWidth: 取值(app, 'default_width', 'defaultWidth') || 800,
    defaultHeight: 取值(app, 'default_height', 'defaultHeight') || 600,
    minWidth: 取值(app, 'min_width', 'minWidth') ?? 600,
    minHeight: 取值(app, 'min_height', 'minHeight') ?? 400,
    resizable: true,
    maximizable: true,
    singleton: 取值(app, 'singleton', 'singleton') ?? false,
    showOnDesktop: 取值(app, 'show_on_desktop', 'showOnDesktop') ?? true,
    showInTray: 取值(app, 'show_in_tray', 'showInTray') ?? false,
    showInLauncher: 取值(app, 'show_in_launcher', 'showInLauncher') ?? false,
    showInSidebar: 取值(app, 'show_in_sidebar', 'showInSidebar') ?? false,
    category: 取值(app, 'category', 'category') || '',
    allowedRoles: 取值(app, 'permissions', 'allowedRoles') || [],
    supportedFileFormats: 取值(app, 'supported_file_formats', 'supportedFileFormats') || undefined,
    windowType: 取值(app, 'window_type', 'windowType') || 'normal',
    allowMultiple: 取值(app, 'allow_multiple', 'allowMultiple') ?? false,
    capabilities: app.capabilities,
    publicActions: app.publicActions,
    enabled: 取值(app, 'enabled', 'enabled') ?? true,
  }
}

export async function loadAppRegistry(role: string): Promise<AppRegistryEntry[]> {
  const response = await fetchDesktopApps()
  if (response.success && Array.isArray(response.data) && response.data.length > 0) {
    const appList = response.data.map(transformApiToEntry)
    setAppRegistry(appList)
    return appList
  }
  throw new Error('Failed to load desktop app registry')
}
