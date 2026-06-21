import { getApp } from '@/desktop/app-registry/app-registry'
import type { WindowState } from './window-types'
import type { DesktopWindowSnapshot } from './desktop-session-storage'
import { deduplicateSnapshots } from './desktop-session-storage'

type RestoreOptions = {
  snapshots: DesktopWindowSnapshot[]
  currentRole?: string
  containerWidth: number
  containerHeight: number
  generateId: () => string
  generateZIndex: () => number
}

export function buildRestoreWindowList(opts: RestoreOptions): WindowState[] {
  const deduped = deduplicateSnapshots(opts.snapshots)
  const result: WindowState[] = []
  for (const snap of [...deduped].sort((a, b) => a.zIndex - b.zIndex)) {
    const reg = getApp(snap.appKey)
    if (!reg || reg.windowType === 'background-service') continue
    if (reg.allowedRoles && opts.currentRole && !reg.allowedRoles.includes(opts.currentRole)) continue

    const width = Math.min(Math.max(reg.minWidth, snap.width), opts.containerWidth)
    const height = Math.min(Math.max(reg.minHeight, snap.height), opts.containerHeight - 48)
    const maximized = Boolean(snap.maximized)
    result.push({
      ...snap,
      id: opts.generateId(),
      title: resolveRestoredWindowTitle(snap.appKey, reg.appName, snap.payload || {}),
      icon: reg.icon,
      x: maximized ? 0 : Math.max(0, Math.min(snap.x, opts.containerWidth - width)),
      y: maximized ? 0 : Math.max(0, Math.min(snap.y, opts.containerHeight - 48 - height)),
      width: maximized ? opts.containerWidth : width,
      height: maximized ? opts.containerHeight - 48 : height,
      zIndex: opts.generateZIndex(),
    })
  }
  if (result.length && !result.some(w => w.isActive && !w.minimized)) {
    const lastWindow = [...result].reverse().find(w => !w.minimized)
    if (lastWindow) lastWindow.isActive = true
  }
  return result
}

function resolveRestoredWindowTitle(appKey: string, defaultTitle: string, payload: Record<string, unknown>): string {
  if (appKey === 'desktop') {
    const folderName = typeof payload.folderName === 'string' ? payload.folderName.trim() : ''
    return folderName ? `${defaultTitle} · ${folderName}` : defaultTitle
  }
  return defaultTitle
}
