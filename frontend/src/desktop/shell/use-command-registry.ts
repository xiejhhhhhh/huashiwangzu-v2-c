import { onMounted, onUnmounted } from 'vue'
import { commandRegistry, getAppOpener, type IDisposable } from '@/desktop/app-registry/command-registry'
import { getApp } from '@/desktop/app-registry/desktop-app-state'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import type { FileEntry } from '@/shared/api/types'
import { formatFileDisplayName } from '@/shared/files/display-name'

export function useCommandRegistry(
  openAppFn: (appKey: string) => unknown,
  executeCommandFn: (command: string) => void,
  openFileFn: (file: FileEntry) => unknown,
) {
  const builtinDisposables: IDisposable[] = []
  let appDisposables: IDisposable[] = []
  let fileDisposables: IDisposable[] = []

  getAppOpener().setOpenApp(openAppFn)
  getAppOpener().setExecuteAction((appKey: string) => openAppFn(appKey))

  function disposeMany(items: IDisposable[]) {
    for (const d of items) d.dispose()
  }

  function registerBuiltinCommands() {
    const builtins: Array<{ id: string; title: string; description?: string; icon?: string; handler: () => void }> = [
      { id: 'builtin:refresh-desktop', title: '刷新桌面', description: '刷新桌面图标和布局', icon: 'RefreshCw', handler: () => executeCommandFn('refresh-desktop') },
      { id: 'builtin:minimize-all', title: '最小化所有窗口', description: '将所有窗口最小化到 Dock', icon: 'Minimize2', handler: () => executeCommandFn('minimize-all') },
      { id: 'builtin:restore-all', title: '还原全部窗口', description: '将所有窗口恢复到正常状态', icon: 'Maximize2', handler: () => executeCommandFn('restore-all') },
      { id: 'builtin:logout', title: '退出登录', description: '注销当前用户', icon: 'LogOut', handler: () => executeCommandFn('logout') },
      // Finder-oriented commands (open files app / common actions)
      { id: 'finder:open', title: '打开访达', description: '打开文件管理器窗口', icon: 'Folder', handler: () => openAppFn('desktop') },
      { id: 'finder:new-window', title: '新建访达窗口', description: '再开一个文件管理器窗口', icon: 'FolderOpen', handler: () => openAppFn('desktop') },
      { id: 'finder:go-documents', title: '前往文稿', description: '打开文稿位置', icon: 'FileText', handler: () => executeCommandFn('finder-go-documents') },
      { id: 'finder:go-downloads', title: '前往下载', description: '打开下载位置', icon: 'Download', handler: () => executeCommandFn('finder-go-downloads') },
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

  function registerAllFiles(fileList: FileEntry[]) {
    disposeMany(fileDisposables)
    fileDisposables = fileList.map(file => commandRegistry.register(
      {
        id: `file:${file.id}`,
        title: file.is_folder
          ? String(file.file_name || '')
          : formatFileDisplayName(file.file_name, file.format),
        description: file.is_folder ? '桌面文件夹' : `${String(file.format || '文件').toUpperCase()} · 桌面文件`,
        icon: file.is_folder ? 'Folder' : 'Document',
        category: '文件',
        resultType: 'file',
      },
      () => openFileFn(file),
      'desktop-files',
    ))
  }

  onMounted(() => {
    registerBuiltinCommands()
  })

  onUnmounted(() => {
    disposeMany(builtinDisposables)
    disposeMany(appDisposables)
    disposeMany(fileDisposables)
    appDisposables = []
    fileDisposables = []
  })

  return { registerAllApps, registerAllFiles, commandRegistry }
}
