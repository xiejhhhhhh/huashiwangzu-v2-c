import type { WindowState } from './window-types'

export type DesktopWindowSnapshot = Omit<WindowState, 'id'>

export const MAX_WINDOWS = 30

export function deduplicateSnapshots(snapshots: DesktopWindowSnapshot[]): DesktopWindowSnapshot[] {
  const desktopWindows = new Map<string, DesktopWindowSnapshot>()
  const others: DesktopWindowSnapshot[] = []

  for (const snap of snapshots) {
    if (snap.appKey === 'desktop') {
      const folderId = snap.payload?.folderId ?? ''
      const key = `desktop::${folderId}`
      const existing = desktopWindows.get(key)
      if (!existing || snap.zIndex > existing.zIndex) {
        desktopWindows.set(key, snap)
      }
    } else {
      others.push(snap)
    }
  }

  const combined = [...others, ...desktopWindows.values()]
  return combined.slice(0, MAX_WINDOWS)
}

export function createDesktopWindowSnapshot(windows: WindowState[]): DesktopWindowSnapshot[] {
  return windows.map(({ id: _id, ...rest }) => rest)
}
