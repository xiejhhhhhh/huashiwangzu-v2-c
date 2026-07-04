/**
 * Desktop app registry - runtime query layer
 *
 * The metadata source of truth is the PostgreSQL system_desktop_apps table,
 * provided to the frontend via API.
 * This file provides role filtering and query helpers. Data is populated
 * by desktop-app-state.ts after API loading.
 */
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { getAppRegistry, getApp as getAppFromState } from '@/desktop/app-registry/desktop-app-state'
import { isLauncherVisibleApp } from './app-visibility'

/** Filter app list by role; returns all if no role provided */
export function getAllowedApps(role?: string): AppRegistryEntry[] {
  const all = Object.values(getAppRegistry())
  if (!role) return all
  const userRole = role.toLowerCase()
  return all.filter(app => {
    const allowed = app.allowedRoles
    return !allowed || allowed.length === 0 || allowed.includes(userRole)
  })
}

/** getDesktopApps, optionally filtered by role */
export function getDesktopApps(role?: string): AppRegistryEntry[] {
  return getAllowedApps(role).filter(a => a.showOnDesktop)
}

/** getApp by key */
export function getApp(key: string): AppRegistryEntry | undefined {
  return getAppFromState(key)
}

/** getTrayApps, optionally filtered by role */
export function getTrayApps(role?: string): AppRegistryEntry[] {
  return getAllowedApps(role).filter(a => a.showInTray)
}

/** getLauncherApps, optionally filtered by role */
export function getLauncherApps(role?: string): AppRegistryEntry[] {
  return getAllowedApps(role).filter(isLauncherVisibleApp)
}

/** getSidebarApps, optionally filtered by role */
export function getSidebarApps(role?: string): AppRegistryEntry[] {
  return getAllowedApps(role).filter(a => a.showInSidebar)
}
