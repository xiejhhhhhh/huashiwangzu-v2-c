import { getActiveDesktopSkinMetrics, type DesktopSkinMetrics } from '@/desktop/skins'

export type { DesktopSkinMetrics }

/** @deprecated Prefer getDesktopChromeMetrics().menuBarHeight — kept for gradual migration. */
export function getMenuBarHeight(): number {
  return getActiveDesktopSkinMetrics().menuBarHeight
}

/** Live chrome metrics from the active shell skin. */
export function getDesktopChromeMetrics(): DesktopSkinMetrics {
  return getActiveDesktopSkinMetrics()
}

/** Compatibility constants — values follow the active skin at call time via getters below. */
export const DESKTOP_MENU_BAR_HEIGHT = 28
export const DESKTOP_DOCK_ICON_SIZE = 48
export const DESKTOP_DOCK_PADDING = 9
export const DESKTOP_DOCK_HEIGHT = 66
export const DESKTOP_DOCK_BOTTOM_GAP = 12
export const DESKTOP_WINDOW_EDGE_GAP = 8

export interface DesktopWorkArea {
  x: number
  y: number
  width: number
  height: number
}

export interface DesktopWindowGeometry {
  x: number
  y: number
  width: number
  height: number
}

export function getDesktopWorkArea(containerWidth: number, containerHeight: number): DesktopWorkArea {
  const metrics = getActiveDesktopSkinMetrics()
  const width = Math.max(0, containerWidth)
  const menuBarHeight = metrics.menuBarHeight
  const dockTop = Math.max(
    menuBarHeight,
    containerHeight - metrics.dockHeight - metrics.dockBottomGap,
  )
  const bottom = Math.max(menuBarHeight, dockTop - metrics.windowEdgeGap)
  return {
    x: 0,
    y: menuBarHeight,
    width,
    height: Math.max(0, bottom - menuBarHeight),
  }
}

export function clampWindowToWorkArea(
  geometry: DesktopWindowGeometry,
  workArea: DesktopWorkArea,
  minWidth = 1,
  minHeight = 1,
): DesktopWindowGeometry {
  const width = Math.min(Math.max(Math.min(minWidth, workArea.width), geometry.width), workArea.width)
  const height = Math.min(Math.max(Math.min(minHeight, workArea.height), geometry.height), workArea.height)
  const maxX = workArea.x + Math.max(0, workArea.width - width)
  const maxY = workArea.y + Math.max(0, workArea.height - height)
  return {
    x: Math.round(Math.max(workArea.x, Math.min(geometry.x, maxX))),
    y: Math.round(Math.max(workArea.y, Math.min(geometry.y, maxY))),
    width: Math.round(width),
    height: Math.round(height),
  }
}
