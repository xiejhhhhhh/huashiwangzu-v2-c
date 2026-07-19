import type { DesktopSkinDefinition } from './types'

/** macOS skin — 中性系统材质（少紫雾、少过亮描边，更接近原生 chrome） */
const menuBarHeight = 28
const dockIconSize = 48
const dockPadding = 8
const dockHeight = dockIconSize + dockPadding * 2 // 64
const dockBottomGap = 10
const workBottomInset = dockHeight + dockBottomGap // 74

export const macosSkin: DesktopSkinDefinition = {
  id: 'macos',
  label: 'macOS',
  metrics: {
    menuBarHeight,
    dockHeight,
    dockPadding,
    dockIconSize,
    dockBottomGap,
    dockRadius: 20,
    windowRadius: 12,
    windowMaximizedRadius: 10,
    windowEdgeGap: 8,
    titlebarHeight: 40,
    workBottomInset,
  },
  cssVars: {
    '--desktop-menu-bar-height': `${menuBarHeight}px`,
    '--desktop-dock-height': `${dockHeight}px`,
    '--desktop-dock-padding': `${dockPadding}px`,
    '--desktop-dock-bottom-gap': `${dockBottomGap}px`,
    '--desktop-work-bottom-inset': `${workBottomInset}px`,
    '--desktop-dock-radius': '20px',
    '--desktop-radius-window': '12px',
    '--window-radius': '12px',
    '--window-maximized-radius': '10px',
    '--window-titlebar-height': '40px',

    /* 中性 macOS 材质 */
    '--desktop-lg-fill': 'rgba(246, 246, 248, 0.42)',
    '--desktop-lg-fill-strong': 'rgba(246, 246, 248, 0.86)',
    '--desktop-lg-fill-panel': 'rgba(242, 242, 247, 0.72)',
    '--desktop-lg-fill-window': 'rgba(246, 246, 248, 0.97)',
    '--desktop-lg-edge': 'rgba(255, 255, 255, 0.36)',
    '--desktop-lg-filter': 'blur(40px) saturate(140%) contrast(1.02)',
    '--desktop-lg-filter-soft': 'blur(28px) saturate(130%)',
    '--desktop-lg-shadow': '0 22px 54px rgba(0, 0, 0, 0.28), 0 4px 14px rgba(0, 0, 0, 0.12), inset 0 0.5px 0 rgba(255, 255, 255, 0.55)',
    '--desktop-lg-shadow-soft': '0 10px 28px rgba(0, 0, 0, 0.22), 0 2px 8px rgba(0, 0, 0, 0.1), inset 0 0.5px 0 rgba(255, 255, 255, 0.42)',

    '--glass-dock-bg': 'rgba(255, 255, 255, 0.22)',
    '--glass-menubar-bg': 'transparent',
    '--glass-menu-bg': 'rgba(246, 246, 248, 0.88)',
    '--glass-panel-bg': 'var(--desktop-lg-fill-panel)',
    '--glass-spotlight-bg': 'rgba(246, 246, 248, 0.9)',
    '--glass-window-bg': 'var(--desktop-lg-fill-window)',
    '--glass-banner-bg': 'var(--desktop-lg-fill-strong)',

    '--desktop-material-border': 'rgba(255, 255, 255, 0.28)',
    '--desktop-material-dock': 'var(--glass-dock-bg)',
    '--desktop-material-menubar': 'var(--glass-menubar-bg)',
    '--desktop-material-popover': 'var(--glass-menu-bg)',
    '--desktop-material-window': 'var(--glass-window-bg)',
    '--desktop-shadow-dock': '0 18px 40px rgba(0, 0, 0, 0.32), 0 2px 8px rgba(0, 0, 0, 0.16), inset 0 0.5px 0 rgba(255, 255, 255, 0.5), inset 0 -0.5px 0 rgba(0, 0, 0, 0.08)',
    '--desktop-shadow-popover': '0 16px 40px rgba(0, 0, 0, 0.24), 0 0 0 0.5px rgba(0, 0, 0, 0.08), inset 0 0.5px 0 rgba(255, 255, 255, 0.55)',
    '--desktop-shadow-window': '0 28px 80px rgba(0, 0, 0, 0.36), 0 8px 24px rgba(0, 0, 0, 0.18), 0 0 0 0.5px rgba(0, 0, 0, 0.2)',
    '--desktop-shadow-window-inactive': '0 10px 28px rgba(0, 0, 0, 0.18), 0 2px 8px rgba(0, 0, 0, 0.08), 0 0 0 0.5px rgba(0, 0, 0, 0.12)',
    '--desktop-liquid-hairline': 'rgba(255, 255, 255, 0.28)',
    '--desktop-liquid-blur-strong': '40px',
    '--desktop-liquid-blur-medium': '28px',
    '--desktop-liquid-blur-light': '18px',
    '--desktop-liquid-blur-spotlight': '40px',
    '--desktop-liquid-saturate': '140%',
    '--window-bg': 'var(--glass-window-bg)',
    '--window-border': 'rgba(0, 0, 0, 0.12)',
    '--window-titlebar-bg': 'rgba(236, 236, 239, 0.88)',
    '--window-titlebar-active-bg': 'rgba(246, 246, 248, 0.94)',
    '--window-titlebar-border': 'rgba(0, 0, 0, 0.06)',
    '--window-content-bg': '#ffffff',
  },
}
