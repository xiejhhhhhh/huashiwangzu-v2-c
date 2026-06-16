import type { WindowState } from './window-types'

export type DesktopWindowSnapshot = Omit<WindowState, 'id'>

export function createDesktopWindowSnapshot(窗口: WindowState[]): DesktopWindowSnapshot[] {
  return 窗口.map(({ id: _id, ...其余 }) => 其余)
}
