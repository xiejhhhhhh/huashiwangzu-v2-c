import { reactive, computed, ref, watch } from 'vue'
import type { WindowState, TaskbarItem } from '@/desktop/window-manager/window-types'
import { getApp } from '@/desktop/app-registry/app-registry'
import { useUserStore } from '@/platform/stores/user'
import { MAX_WINDOWS, type DesktopWindowSnapshot } from './desktop-session-storage'
import { buildRestoreWindowList } from './desktop-session-restore'
import { clampWindowToWorkArea, getDesktopWorkArea } from '@/desktop/config/desktop-chrome-metrics'

const WINDOW_TYPE_BACKGROUND_SERVICE = 'background-service'
const WINDOW_TYPE_NORMAL = 'normal'
type WindowGeometry = { x: number; y: number; width: number; height: number }

const windows = reactive<WindowState[]>([])
let nextZIndex = 100
let nextId = 1
const desktopContainerSize = reactive({ width: window.innerWidth, height: window.innerHeight })
const showDesktopWindowIds = new Set<string>()

function canonicalAppKey(appKey: string): string {
  return getApp(appKey)?.canonicalAppKey || appKey
}

function generateId(): string { return `win_${Date.now()}_${nextId++}` }

function generateZIndex(): number { return nextZIndex++ }

const taskbarItems = ref<TaskbarItem[]>([])
watch(() => windows.map(w => ({
  id: w.id, title: w.title, icon: w.icon,
  isActive: w.isActive, minimized: w.minimized, appKey: w.appKey,
})), (value) => { taskbarItems.value = value }, { immediate: true, deep: true })

function openWindow(appKey: string, payload?: unknown, originRect?: WindowGeometry): string | null {
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
    const existingWindow = windows.find(w => canonicalAppKey(w.appKey) === canonicalAppKey(appKey))
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

  const workArea = getDesktopWorkArea(desktopContainerSize.width, desktopContainerSize.height)
  const geometry = clampWindowToWorkArea({
    x: app.defaultWidth > 800 ? 120 + offset : 160 + offset,
    y: workArea.y + 54 + offset,
    width: app.defaultWidth,
    height: app.defaultHeight,
  }, workArea, app.minWidth, app.minHeight)

  windows.push({
    id, appKey,
    title: resolveWindowTitle(appKey, app.appName, windowPayload), icon: app.icon,
    ...geometry,
    zIndex: nextZIndex++,
    minimized: false, maximized: false, isActive: true,
    windowType: app.windowType || WINDOW_TYPE_NORMAL,
    payload: windowPayload,
    animationOrigin: originRect || undefined,
  })

  // 动画来源坐标是一次性信息，200ms后清除
  if (originRect) {
    setTimeout(() => {
      const w = windows.find(win => win.id === id)
      if (w) w.animationOrigin = undefined
    }, 200)
  }

  windows.forEach(w => { if (w.id !== id) w.isActive = false })
  return id
}

function closeWindow(id: string) {
  const idx = windows.findIndex(w => w.id === id)
  if (idx === -1) return
  const wasActive = windows[idx].isActive
  windows.splice(idx, 1)
  showDesktopWindowIds.delete(id)
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

function minimizeWindow(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w || w.minimized) return
  w.minimized = true
  w.isActive = false
  activateTopmostVisibleWindow(w.id)
}

function restoreWindow(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  w.minimized = false
  activateWindow(id)
}

function toggleMaximized(id: string, restoreState?: WindowGeometry) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  if (w.maximized) {
    const workArea = getDesktopWorkArea(desktopContainerSize.width, desktopContainerSize.height)
    if (w.preMaximizeState) {
      Object.assign(w, clampWindowToWorkArea(w.preMaximizeState, workArea))
    }
    w.maximized = false
  } else {
    w.preMaximizeState = restoreState ? { ...restoreState } : { x: w.x, y: w.y, width: w.width, height: w.height }
    const workArea = getDesktopWorkArea(desktopContainerSize.width, desktopContainerSize.height)
    w.x = workArea.x; w.y = workArea.y
    w.width = workArea.width
    w.height = workArea.height
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
  const workArea = getDesktopWorkArea(width, height)
  for (const w of windows) {
    if (w.maximized) {
      w.x = workArea.x
      w.y = workArea.y
      w.width = workArea.width
      w.height = workArea.height
      continue
    }
    const app = getApp(w.appKey)
    Object.assign(w, clampWindowToWorkArea(w, workArea, app?.minWidth, app?.minHeight))
  }
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
  if (w && !w.maximized) {
    const app = getApp(w.appKey)
    const workArea = getDesktopWorkArea(desktopContainerSize.width, desktopContainerSize.height)
    Object.assign(w, clampWindowToWorkArea({ x, y, width, height }, workArea, app?.minWidth, app?.minHeight))
  }
}

function showDesktop() {
  showDesktopWindowIds.clear()
  for (const w of windows) {
    if (w.minimized || w.windowType === WINDOW_TYPE_BACKGROUND_SERVICE) continue
    showDesktopWindowIds.add(w.id)
    w.minimized = true
    w.isActive = false
  }
}

function restoreDesktop() {
  const ids = [...showDesktopWindowIds]
  showDesktopWindowIds.clear()
  for (const id of ids) {
    const w = windows.find(item => item.id === id)
    if (w) w.minimized = false
  }
  const top = windows.filter(w => !w.minimized).sort((a, b) => b.zIndex - a.zIndex)[0]
  if (top) activateWindow(top.id)
}

function toggleDesktopVisibility() {
  if (showDesktopWindowIds.size > 0) restoreDesktop()
  else showDesktop()
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
      const existingWindow = windows.find(x => canonicalAppKey(x.appKey) === canonicalAppKey(w.appKey) && x.minimized === w.minimized)
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
    openWindow, closeWindow, toggleMinimized, minimizeWindow, restoreWindow, toggleMaximized, activateWindow,
    updateWindowPosition, updateWindowSize, updateWindowGeometry,
    setContainerSize, restoreWindows, showDesktop, restoreDesktop, toggleDesktopVisibility,
  }
}

export const windowManager = {
  windows,
  get openedWindowCount() { return windows.length },
  taskbarItems,
  openWindow, closeWindow, toggleMinimized, minimizeWindow, restoreWindow, toggleMaximized, activateWindow,
  updateWindowPosition, updateWindowSize, updateWindowGeometry,
  setContainerSize, restoreWindows, showDesktop, restoreDesktop, toggleDesktopVisibility,
}
