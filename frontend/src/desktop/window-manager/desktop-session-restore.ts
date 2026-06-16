import { getApp } from '@/desktop/app-registry/app-registry'
import type { WindowState } from './window-types'
import type { DesktopWindowSnapshot } from './desktop-session-storage'

type RestoreOptions = {
  快照: DesktopWindowSnapshot[]
  当前角色?: string
  容器宽: number
  容器高: number
  生成id: () => string
  生成层级: () => number
}

export function buildRestoreWindowList(参数: RestoreOptions): WindowState[] {
  const 结果: WindowState[] = []
  for (const 项 of [...参数.快照].sort((a, b) => a.zIndex - b.zIndex)) {
    const 应用 = getApp(项.appKey)
    if (!应用 || 应用.windowType === '后台服务') continue
    if (应用.allowedRoles && 参数.当前角色 && !应用.allowedRoles.includes(参数.当前角色)) continue

    const width = Math.min(Math.max(应用.minWidth, 项.width), 参数.容器宽)
    const height = Math.min(Math.max(应用.minHeight, 项.height), 参数.容器高 - 48)
    const maximized = Boolean(项.maximized)
    结果.push({
      ...项,
      id: 参数.生成id(),
      title: 应用.appName,
      icon: 应用.icon,
      x: maximized ? 0 : Math.max(0, Math.min(项.x, 参数.容器宽 - width)),
      y: maximized ? 0 : Math.max(0, Math.min(项.y, 参数.容器高 - 48 - height)),
      width: maximized ? 参数.容器宽 : width,
      height: maximized ? 参数.容器高 - 48 : height,
      zIndex: 参数.生成层级(),
    })
  }
  if (结果.length && !结果.some(w => w.isActive && !w.minimized)) {
    const 最后窗口 = [...结果].reverse().find(w => !w.minimized)
    if (最后窗口) 最后窗口.isActive = true
  }
  return 结果
}
