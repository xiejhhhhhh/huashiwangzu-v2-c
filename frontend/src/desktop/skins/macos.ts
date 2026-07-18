import type { DesktopSkinDefinition } from './types'

/** macOS skin — V3.1 consistency (fevze recipe + our shell capabilities). */
const menuBarHeight = 28
const dockIconSize = 48
const dockPadding = 9
const dockHeight = dockIconSize + dockPadding * 2 // 66
const dockBottomGap = 12
const workBottomInset = dockHeight + dockBottomGap // 78

export const macosSkin: DesktopSkinDefinition = {
  id: 'macos',
  label: 'macOS',
  metrics: {
    menuBarHeight,
    dockHeight,
    dockPadding,
    dockIconSize,
    dockBottomGap,
    dockRadius: 18,
    windowRadius: 14,
    windowMaximizedRadius: 12,
    windowEdgeGap: 8,
    titlebarHeight: 44,
    workBottomInset,
  },
  cssVars: {
    '--desktop-menu-bar-height': `${menuBarHeight}px`,
    '--desktop-dock-height': `${dockHeight}px`,
    '--desktop-dock-padding': `${dockPadding}px`,
    '--desktop-dock-bottom-gap': `${dockBottomGap}px`,
    '--desktop-work-bottom-inset': `${workBottomInset}px`,
    '--desktop-dock-radius': '18px',
    '--desktop-radius-window': '14px',
    '--window-radius': '14px',
    '--window-maximized-radius': '12px',
    '--window-titlebar-height': '44px',

    /* single liquid-glass recipe (fevze-inspired) */
    '--desktop-lg-fill': 'rgba(248, 247, 252, 0.36)',
    '--desktop-lg-fill-strong': 'rgba(249, 248, 252, 0.82)',
    '--desktop-lg-fill-panel': 'rgba(246, 246, 250, 0.66)',
    '--desktop-lg-fill-window': 'rgba(246, 246, 248, 0.94)',
    '--desktop-lg-edge': 'rgba(255, 255, 255, 0.58)',
    '--desktop-lg-filter': 'blur(34px) saturate(182%) contrast(1.03)',
    '--desktop-lg-filter-soft': 'blur(24px) saturate(160%)',
    '--desktop-lg-shadow': '0 26px 68px rgba(22, 17, 42, 0.25), 0 6px 18px rgba(22, 17, 42, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.52)',
    '--desktop-lg-shadow-soft': '0 14px 36px rgba(22, 17, 42, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.4)',

    '--glass-dock-bg': 'rgba(239, 235, 246, 0.48)',
    '--glass-menubar-bg': 'rgba(248, 244, 252, 0.42)',
    '--glass-menu-bg': 'var(--desktop-lg-fill-strong)',
    '--glass-panel-bg': 'var(--desktop-lg-fill-panel)',
    '--glass-spotlight-bg': 'var(--desktop-lg-fill-strong)',
    '--glass-window-bg': 'var(--desktop-lg-fill-window)',
    '--glass-banner-bg': 'var(--desktop-lg-fill-strong)',

    '--desktop-material-border': 'var(--desktop-lg-edge)',
    '--desktop-material-dock': 'var(--glass-dock-bg)',
    '--desktop-material-menubar': 'var(--glass-menubar-bg)',
    '--desktop-material-popover': 'var(--glass-menu-bg)',
    '--desktop-material-window': 'var(--glass-window-bg)',
    '--desktop-shadow-dock': 'var(--desktop-lg-shadow-soft)',
    '--desktop-shadow-popover': 'var(--desktop-lg-shadow-soft)',
    '--desktop-shadow-window': '0 24px 72px rgba(0,0,0,.32), 0 2px 12px rgba(0,0,0,.16), 0 0 0 .5px rgba(0,0,0,.18)',
    '--desktop-shadow-window-inactive': '0 12px 36px rgba(0,0,0,.2), 0 0 0 .5px rgba(0,0,0,.14)',
    '--desktop-liquid-hairline': 'var(--desktop-lg-edge)',
    '--desktop-liquid-blur-strong': '34px',
    '--desktop-liquid-blur-medium': '34px',
    '--desktop-liquid-blur-light': '20px',
    '--desktop-liquid-blur-spotlight': '34px',
    '--desktop-liquid-saturate': '182%',
    '--window-bg': 'var(--glass-window-bg)',
    '--window-border': 'rgba(255, 255, 255, 0.42)',
  },
}
