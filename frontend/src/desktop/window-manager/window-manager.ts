import { reactive, computed, ref, watch } from 'vue'
import type { WindowState, TaskbarItem } from '@/desktop/window-manager/window-types'
import { getApp } from '@/desktop/app-registry/app-registry'
import { useUserStore } from '@/platform/stores/user'
import { MAX_WINDOWS, type DesktopWindowSnapshot } from './desktop-session-storage'
import { buildRestoreWindowList } from './desktop-session-restore'

const WINDOW_TYPE_BACKGROUND_SERVICE = 'background-service'
const WINDOW_TYPE_NORMAL = 'normal'
type WindowGeometry = { x: number; y: number; width: number; height: number }

const windows = reactive<WindowState[]>([])
let nextZIndex = 100
let nextId = 1
const desktopContainerSize = reactive({ width: window.innerWidth, height: window.innerHeight })

function generateId(): string { return `win_${Date.now()}_${nextId++}` }

function generateZIndex(): number { return nextZIndex++ }

const taskbarItems = ref<TaskbarItem[]>([])
watch(() => windows.map(w => ({
  id: w.id, title: w.title, icon: w.icon,
  isActive: w.isActive, minimized: w.minimized,
})), (value) => { taskbarItems.value = value }, { immediate: true, deep: true })

function openWindow(appKey: string, payload?: unknown): string | null {
  const app = getApp(appKey)
  if (!app) return null
  const store = useUserStore()
  const currentRole = store.userInfo?.role?.toLowerCase()
  if (app.allowedRoles && app.allowedRoles.length > 0 && currentRole && !app.allowedRoles.includes(currentRole)) {
    console.warn(`Opening window was denied: role ${currentRole} cannot access app ${appKey}`)
    return null
  }

  if (app.windowType === WINDOW_TYPE_BACKGROUND_SERVICE) {
    const existingService = windows.find(w => w.appKey === appKey)
    if (existingService) { activateWindow(existingService.id); return existingService.id }
    console.warn(`Background service ${appKey} does not support window mode`)
    return null
  }

  if (!app.allowMultiple) {
    const existingWindow = windows.find(w => w.appKey === appKey)
    if (existingWindow) {
      updateWindowPayload(existingWindow.id, payload)
      activateWindow(existingWindow.id)
      existingWindow.minimized = false
      return existingWindow.id
    }
  }

  if (appKey === 'desktop') {
    const normPayload = normalizeWindowPayload(payload)
    const targetFolderId = normPayload?.folderId ?? null
    const existingDesktop = windows.find(w =>
      w.appKey === 'desktop' && (w.payload?.folderId ?? null) === targetFolderId
    )
    if (existingDesktop) {
      updateWindowPayload(existingDesktop.id, payload)
      activateWindow(existingDesktop.id)
      existingDesktop.minimized = false
      return existingDesktop.id
    }
  }

  if (windows.length >= MAX_WINDOWS) {
    console.warn(`Window limit (${MAX_WINDOWS}) reached, cannot open more windows`)
    return null
  }

  const offset = (windows.length % 10) * 30
  const id = generateId()
  const windowPayload = normalizeWindowPayload(payload)

  windows.push({
    id, appKey,
    title: resolveWindowTitle(appKey, app.appName, windowPayload), icon: app.icon,
    x: app.defaultWidth > 800 ? 120 + offset : 160 + offset,
    y: 110 + offset,
    width: app.defaultWidth, height: app.defaultHeight,
    zIndex: nextZIndex++,
    minimized: false, maximized: false, isActive: true,
    windowType: app.windowType || WINDOW_TYPE_NORMAL,
    payload: windowPayload,
  })

  windows.forEach(w => { if (w.id !== id) w.isActive = false })
  return id
}

function closeWindow(id: string) {
  const idx = windows.findIndex(w => w.id === id)
  if (idx === -1) return
  const wasActive = windows[idx].isActive
  windows.splice(idx, 1)
  if (wasActive) activateTopmostVisibleWindow()
}

function toggleMinimized(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  w.minimized = !w.minimized
  if (w.minimized) {
    w.isActive = false
    activateTopmostVisibleWindow(w.id)
  } else { activateWindow(id) }
}

function toggleMaximized(id: string, restoreState?: WindowGeometry) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  if (w.maximized) {
    if (w.preMaximizeState) { w.x = w.preMaximizeState.x; w.y = w.preMaximizeState.y; w.width = w.preMaximizeState.width; w.height = w.preMaximizeState.height }
    w.maximized = false
  } else {
    w.preMaximizeState = restoreState ? { ...restoreState } : { x: w.x, y: w.y, width: w.width, height: w.height }
    w.x = 0; w.y = 0
    w.width = desktopContainerSize.width
    w.height = desktopContainerSize.height - 48
    w.maximized = true
  }
}

function activateWindow(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  windows.forEach(x => x.isActive = false)
  w.isActive = true; w.zIndex = nextZIndex++; w.minimized = false
}

function activateTopmostVisibleWindow(excludeId?: string) {
  const next = windows
    .filter(w => w.id !== excludeId && !w.minimized && w.windowType !== WINDOW_TYPE_BACKGROUND_SERVICE)
    .sort((a, b) => b.zIndex - a.zIndex)[0]
  if (!next) return
  windows.forEach(w => { w.isActive = false })
  next.isActive = true
  next.zIndex = nextZIndex++
}

function setContainerSize(width: number, height: number) {
  desktopContainerSize.width = width
  desktopContainerSize.height = height
}

function updateWindowPosition(id: string, x: number, y: number) {
  const w = windows.find(win => win.id === id)
  if (!w || w.maximized) return
  w.x = x
  w.y = y
}

function updateWindowSize(id: string, width: number, height: number) {
  const w = windows.find(win => win.id === id)
  if (w && !w.maximized) { w.width = width; w.height = height }
}

function updateWindowGeometry(id: string, x: number, y: number, width: number, height: number) {
  const w = windows.find(win => win.id === id)
  if (w && !w.maximized) { w.x = x; w.y = y; w.width = width; w.height = height }
}

function normalizeWindowPayload(payload?: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return {}
  return { ...(payload as Record<string, unknown>) }
}

function resolveWindowTitle(appKey: string, defaultTitle: string, payload: Record<string, unknown>): string {
  if (appKey === 'desktop') {
    const folderName = typeof payload.folderName === 'string' ? payload.folderName.trim() : ''
    return folderName ? `${defaultTitle} · ${folderName}` : defaultTitle
  }
  return defaultTitle
}

function updateWindowPayload(id: string, payload?: unknown) {
  const w = windows.find(win => win.id === id)
  if (!w) return
  const nextPayload = normalizeWindowPayload(payload)
  w.payload = { ...(w.payload || {}), ...nextPayload }
  const app = getApp(w.appKey)
  if (app) {
    w.title = resolveWindowTitle(w.appKey, app.appName, w.payload)
  }
}

function restoreWindows(snapshot: DesktopWindowSnapshot[], currentRole?: string) {
  windows.splice(0, windows.length)
  const restoredWindows = buildRestoreWindowList({
    snapshots: snapshot,
    currentRole,
    containerWidth: desktopContainerSize.width,
    containerHeight: desktopContainerSize.height,
    generateId,
    generateZIndex,
  })
  for (const w of restoredWindows) {
    const app = getApp(w.appKey)
    if (app && !app.allowMultiple) {
      const existingWindow = windows.find(x => x.appKey === w.appKey && x.minimized === w.minimized)
      if (existingWindow) { activateWindow(existingWindow.id); continue }
    }
    windows.push(w)
  }
}

export function useWindowManager() {
  return {
    windows,
    openedWindowCount: computed(() => windows.length),
    taskbarItems,
    openWindow, closeWindow, toggleMinimized, toggleMaximized, activateWindow,
    updateWindowPosition, updateWindowSize, updateWindowGeometry,
    setContainerSize, restoreWindows,
  }
}

export const windowManager = {
  windows,
  get openedWindowCount() { return windows.length },
  taskbarItems,
  openWindow, closeWindow, toggleMinimized, toggleMaximized, activateWindow,
  updateWindowPosition, updateWindowSize, updateWindowGeometry,
  setContainerSize, restoreWindows,
}
