import type { DesktopSkinDefinition } from './types'

/**
 * Win11 skin slot — metrics + material tokens only.
 * Full Win11 chrome (centered taskbar icons, snap flyouts, mica) can fill this later
 * without changing window/product runtime.
 */
const menuBarHeight = 0
const dockIconSize = 40
const dockPadding = 6
const dockHeight = 48
const dockBottomGap = 0
const workBottomInset = dockHeight + dockBottomGap

export const win11Skin: DesktopSkinDefinition = {
  id: 'win11',
  label: 'Windows 11',
  metrics: {
    menuBarHeight,
    dockHeight,
    dockPadding,
    dockIconSize,
    dockBottomGap,
    dockRadius: 0,
    windowRadius: 8,
    windowMaximizedRadius: 0,
    windowEdgeGap: 0,
    titlebarHeight: 32,
    workBottomInset,
  },
  cssVars: {
    '--desktop-menu-bar-height': `${menuBarHeight}px`,
    '--desktop-dock-height': `${dockHeight}px`,
    '--desktop-dock-padding': `${dockPadding}px`,
    '--desktop-dock-bottom-gap': `${dockBottomGap}px`,
    '--desktop-work-bottom-inset': `${workBottomInset}px`,
    '--desktop-dock-radius': '0px',
    '--desktop-radius-window': '8px',
    '--window-radius': '8px',
    '--window-maximized-radius': '0px',
    '--window-titlebar-height': '32px',

    /* Mica / acrylic-ish starter recipe (not final Win11 polish) */
    '--desktop-lg-fill': 'rgba(243, 243, 243, 0.72)',
    '--desktop-lg-fill-strong': 'rgba(252, 252, 252, 0.92)',
    '--desktop-lg-fill-panel': 'rgba(249, 249, 249, 0.88)',
    '--desktop-lg-fill-window': 'rgba(255, 255, 255, 0.96)',
    '--desktop-lg-edge': 'rgba(0, 0, 0, 0.08)',
    '--desktop-lg-filter': 'blur(40px) saturate(140%)',
    '--desktop-lg-filter-soft': 'blur(20px) saturate(130%)',
    '--desktop-lg-shadow': '0 8px 24px rgba(0, 0, 0, 0.14), 0 2px 6px rgba(0, 0, 0, 0.08)',
    '--desktop-lg-shadow-soft': '0 4px 16px rgba(0, 0, 0, 0.12)',

    '--glass-dock-bg': 'rgba(243, 243, 243, 0.78)',
    '--glass-menubar-bg': 'transparent',
    '--glass-menu-bg': 'var(--desktop-lg-fill-strong)',
    '--glass-panel-bg': 'var(--desktop-lg-fill-panel)',
    '--glass-spotlight-bg': 'var(--desktop-lg-fill-strong)',
    '--glass-window-bg': 'var(--desktop-lg-fill-window)',
    '--glass-banner-bg': 'var(--desktop-lg-fill-strong)',

    '--desktop-material-border': 'var(--desktop-lg-edge)',
    '--desktop-material-dock': 'var(--glass-dock-bg)',
    '--desktop-material-menubar': 'transparent',
    '--desktop-material-popover': 'var(--glass-menu-bg)',
    '--desktop-material-window': 'var(--glass-window-bg)',
    '--desktop-shadow-dock': '0 -1px 0 rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.12)',
    '--desktop-shadow-popover': 'var(--desktop-lg-shadow-soft)',
    '--desktop-shadow-window': '0 16px 48px rgba(0,0,0,.18), 0 0 0 1px rgba(0,0,0,.06)',
    '--desktop-shadow-window-inactive': '0 8px 24px rgba(0,0,0,.12), 0 0 0 1px rgba(0,0,0,.05)',
    '--desktop-liquid-hairline': 'var(--desktop-lg-edge)',
    '--desktop-liquid-blur-strong': '40px',
    '--desktop-liquid-blur-medium': '40px',
    '--desktop-liquid-blur-light': '16px',
    '--desktop-liquid-blur-spotlight': '40px',
    '--desktop-liquid-saturate': '140%',
    '--desktop-system-blue': '#0067c0',
    '--desktop-selection': '#0067c0',
    '--window-bg': 'var(--glass-window-bg)',
    '--window-border': 'rgba(0, 0, 0, 0.08)',
  },
}
