import { getApp } from '@/desktop/app-registry/app-registry'
import type { WindowState } from './window-types'
import type { DesktopWindowSnapshot } from './desktop-session-storage'
import { deduplicateSnapshots } from './desktop-session-storage'
import { clampWindowToWorkArea, getDesktopWorkArea } from '@/desktop/config/desktop-chrome-metrics'

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
  const workArea = getDesktopWorkArea(opts.containerWidth, opts.containerHeight)
  const singletonKeys = new Set<string>()
  for (const snap of [...deduped].sort((a, b) => a.zIndex - b.zIndex)) {
    const reg = getApp(snap.appKey)
    if (!reg || reg.windowType === 'background-service') continue
    if (reg.allowedRoles && opts.currentRole && !reg.allowedRoles.includes(opts.currentRole)) continue
    const canonicalKey = reg.canonicalAppKey || reg.appKey
    if (!reg.allowMultiple && singletonKeys.has(canonicalKey)) continue
    if (!reg.allowMultiple) singletonKeys.add(canonicalKey)

    const geometry = clampWindowToWorkArea(snap, workArea, reg.minWidth, reg.minHeight)
    const maximized = Boolean(snap.maximized)
    const restoredGeometry = maximized
      ? { x: workArea.x, y: workArea.y, width: workArea.width, height: workArea.height }
      : avoidRestoredOverlap(geometry, result, workArea, reg.minWidth, reg.minHeight)
    result.push({
      ...snap,
      id: opts.generateId(),
      title: resolveRestoredWindowTitle(snap.appKey, reg.appName, snap.payload || {}),
      icon: reg.icon,
      x: restoredGeometry.x,
      y: restoredGeometry.y,
      width: restoredGeometry.width,
      height: restoredGeometry.height,
      zIndex: opts.generateZIndex(),
    })
  }
  if (result.length && !result.some(w => w.isActive && !w.minimized)) {
    const lastWindow = [...result].reverse().find(w => !w.minimized)
    if (lastWindow) lastWindow.isActive = true
  }
  return result
}

function avoidRestoredOverlap(
  geometry: ReturnType<typeof clampWindowToWorkArea>,
  restored: WindowState[],
  workArea: ReturnType<typeof getDesktopWorkArea>,
  minWidth: number,
  minHeight: number,
) {
  let candidate = geometry
  for (let attempt = 0; attempt < restored.length + 1; attempt += 1) {
    const overlaps = restored.some((window) =>
      window.x === candidate.x
      && window.y === candidate.y
      && window.width === candidate.width
      && window.height === candidate.height,
    )
    if (!overlaps) return candidate
    candidate = clampWindowToWorkArea({
      ...candidate,
      x: candidate.x + 28,
      y: candidate.y + 28,
    }, workArea, minWidth, minHeight)
  }
  return candidate
}

function resolveRestoredWindowTitle(appKey: string, defaultTitle: string, payload: Record<string, unknown>): string {
  if (appKey === 'desktop') {
    const folderName = typeof payload.folderName === 'string' ? payload.folderName.trim() : ''
    return folderName ? `${defaultTitle} · ${folderName}` : defaultTitle
  }
  return defaultTitle
}
