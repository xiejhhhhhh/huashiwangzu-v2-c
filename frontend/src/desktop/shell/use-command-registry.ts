import { onMounted, onUnmounted } from 'vue'
import { commandRegistry, getAppOpener, type IDisposable } from '@/desktop/app-registry/command-registry'
import { getApp } from '@/desktop/app-registry/desktop-app-state'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'

export function useCommandRegistry(
  openAppFn: (appKey: string) => void,
  executeCommandFn: (command: string) => void,
) {
  const builtinDisposables: IDisposable[] = []
  let appDisposables: IDisposable[] = []

  getAppOpener().setOpenApp(openAppFn)
  getAppOpener().setExecuteAction((appKey: string) => openAppFn(appKey))

  function disposeMany(items: IDisposable[]) {
    for (const d of items) d.dispose()
  }

  function registerBuiltinCommands() {
    const builtins: Array<{ id: string; title: string; description?: string; icon?: string; handler: () => void }> = [
      { id: 'builtin:refresh-desktop', title: '刷新桌面', description: '刷新桌面图标和布局', icon: '🔄', handler: () => executeCommandFn('refresh-desktop') },
      { id: 'builtin:minimize-all', title: '最小化所有窗口', description: '将所有窗口最小化到任务栏', icon: '🪟', handler: () => executeCommandFn('minimize-all') },
      { id: 'builtin:restore-all', title: '还原全部窗口', description: '将所有窗口恢复到正常状态', icon: '📐', handler: () => executeCommandFn('restore-all') },
      { id: 'builtin:logout', title: '退出登录', description: '注销当前用户', icon: '🚪', handler: () => executeCommandFn('logout') },
    ]
    for (const c of builtins) {
      builtinDisposables.push(
        commandRegistry.register(
          { id: c.id, title: c.title, description: c.description, icon: c.icon, category: '系统工具' },
          c.handler,
          'builtin',
        ),
      )
    }
  }

  function registerAllApps(appList: AppRegistryEntry[]) {
    disposeMany(appDisposables)
    appDisposables = []
    for (const app of appList) {
      const ds = commandRegistry.registerAppEntry(app)
      appDisposables.push(...ds)
    }
  }

  onMounted(() => {
    registerBuiltinCommands()
  })

  onUnmounted(() => {
    disposeMany(builtinDisposables)
    disposeMany(appDisposables)
    appDisposables = []
  })

  return { registerAllApps, commandRegistry }
}
