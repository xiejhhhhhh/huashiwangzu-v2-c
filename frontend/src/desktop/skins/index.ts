import { macosSkin } from './macos'
import { win11Skin } from './win11'
import type { DesktopShellSkinId, DesktopSkinDefinition, DesktopSkinMetrics } from './types'
import { DESKTOP_SKIN_STORAGE_KEY } from './types'

export type { DesktopShellSkinId, DesktopSkinDefinition, DesktopSkinMetrics }
export { DESKTOP_SKIN_STORAGE_KEY }

export const DESKTOP_SKINS: Record<DesktopShellSkinId, DesktopSkinDefinition> = {
  macos: macosSkin,
  win11: win11Skin,
}

export const DEFAULT_DESKTOP_SKIN: DesktopShellSkinId = 'macos'

let activeSkinId: DesktopShellSkinId = DEFAULT_DESKTOP_SKIN

export function isDesktopShellSkinId(value: unknown): value is DesktopShellSkinId {
  return value === 'macos' || value === 'win11'
}

export function getDesktopSkin(id?: DesktopShellSkinId): DesktopSkinDefinition {
  return DESKTOP_SKINS[id && isDesktopShellSkinId(id) ? id : activeSkinId] || macosSkin
}

export function getActiveDesktopSkinId(): DesktopShellSkinId {
  return activeSkinId
}

export function getActiveDesktopSkinMetrics(): DesktopSkinMetrics {
  return getDesktopSkin(activeSkinId).metrics
}

/** Read persisted preference without applying DOM (safe for SSR/tests). */
export function readStoredDesktopSkin(): DesktopShellSkinId {
  if (typeof window === 'undefined') return DEFAULT_DESKTOP_SKIN
  try {
    const raw = window.localStorage.getItem(DESKTOP_SKIN_STORAGE_KEY)
    if (isDesktopShellSkinId(raw)) return raw
  } catch {
    /* ignore */
  }
  return DEFAULT_DESKTOP_SKIN
}

export function persistDesktopSkin(id: DesktopShellSkinId): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(DESKTOP_SKIN_STORAGE_KEY, id)
  } catch {
    /* ignore */
  }
}

/**
 * Apply skin CSS variables + data attributes onto a host element (shell root preferred).
 * Also mirrors onto documentElement so portals (Teleport menus/toasts) inherit tokens.
 */
export function applyDesktopSkin(id: DesktopShellSkinId, host?: HTMLElement | null): DesktopSkinDefinition {
  const skin = getDesktopSkin(id)
  activeSkinId = skin.id

  const targets: HTMLElement[] = []
  if (typeof document !== 'undefined') {
    targets.push(document.documentElement)
    if (host) targets.push(host)
  } else if (host) {
    targets.push(host)
  }

  for (const el of targets) {
    el.dataset.desktopSkin = skin.id
    for (const [key, value] of Object.entries(skin.cssVars)) {
      el.style.setProperty(key, value)
    }
  }

  return skin
}

export function listDesktopSkins(): Array<{ id: DesktopShellSkinId; label: string }> {
  return Object.values(DESKTOP_SKINS).map(skin => ({ id: skin.id, label: skin.label }))
}
