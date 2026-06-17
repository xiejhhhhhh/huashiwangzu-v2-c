import { defineComponent, h } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { fetchDesktopApps } from '@/shared/api/desktop-apps'
import type { DesktopAppItem } from '@/shared/api/desktop-apps'
import { componentKeyMap } from '@/desktop/app-registry/component-key-map'
import { setAppRegistry } from '@/desktop/app-registry/desktop-app-state'
import ComponentRegistrationError from '@/desktop/components/component-registration-error.vue'

function missingComponentLoader(app: DesktopAppItem, componentKey: string): AppRegistryEntry['entryComponent'] {
  const appKey = app.app_id || ''
  const appName = app.name || ''
  console.error(`[app-registry] Missing component loader for ${appKey || appName || 'unknown app'}: ${componentKey || '<empty>'}`)
  return () => Promise.resolve({
    default: defineComponent({
      name: 'MissingDesktopAppComponent',
      setup() {
        return () => h(ComponentRegistrationError, { appKey, appName, componentKey })
      },
    }),
  })
}

function transformApiToEntry(app: DesktopAppItem): AppRegistryEntry {
  const entryKey: string = app.entry_component_key || ''
  const componentLoader = componentKeyMap[entryKey]
  return {
    appKey: app.app_id || '',
    appName: app.name || '',
    icon: app.icon,
    description: app.description,
    entryComponent: componentLoader || missingComponentLoader(app, entryKey),
    defaultWidth: app.default_width || 800,
    defaultHeight: app.default_height || 600,
    minWidth: app.min_width ?? 600,
    minHeight: app.min_height ?? 400,
    resizable: true,
    maximizable: true,
    singleton: app.singleton ?? false,
    showOnDesktop: app.show_on_desktop ?? true,
    showInTray: app.show_in_tray ?? false,
    showInLauncher: app.show_in_launcher ?? false,
    showInSidebar: app.show_in_sidebar ?? false,
    category: app.category || '',
    allowedRoles: app.permissions || [],
    supportedFormats: app.supported_formats || undefined,
    editableFormats: app.editable_formats || undefined,
    creatableFormats: app.creatable_formats || undefined,
    sortOrder: app.sort_order ?? 0,
    windowType: app.window_type || 'normal',
    allowMultiple: app.allow_multiple ?? false,
    capabilities: app.capabilities,
    publicActions: app.public_actions,
    enabled: app.enabled ?? true,
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
