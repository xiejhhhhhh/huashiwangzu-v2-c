/**
 * Desktop shell skin contract.
 *
 * Behavior (window manager, products, files, open resolver) stays skin-agnostic.
 * Skins only supply chrome metrics + CSS variables applied on the shell root.
 */
export type DesktopShellSkinId = 'macos' | 'win11'

export interface DesktopSkinMetrics {
  /** Top chrome height (mac menu bar / win title strip). 0 allowed for pure taskbar layouts. */
  menuBarHeight: number
  /** Bottom chrome outer height (dock / taskbar). */
  dockHeight: number
  dockPadding: number
  dockIconSize: number
  dockBottomGap: number
  dockRadius: number
  windowRadius: number
  windowMaximizedRadius: number
  windowEdgeGap: number
  titlebarHeight: number
  /** CSS length for work-area bottom inset (usually dockHeight + dockBottomGap). */
  workBottomInset: number
}

export interface DesktopSkinDefinition {
  id: DesktopShellSkinId
  label: string
  metrics: DesktopSkinMetrics
  /**
   * CSS custom properties applied to the shell host (and optionally :root while active).
   * Keys must be full custom property names including leading --.
   */
  cssVars: Record<string, string>
}

export const DESKTOP_SKIN_STORAGE_KEY = 'desktop.shellSkin'
