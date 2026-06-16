import { reactive, computed, ref, watch } from 'vue'
import type { WindowState, TaskbarItem } from '@/desktop/window-manager/window-types'
import { getApp } from '@/desktop/app-registry/app-registry'
import { useUserStore } from '@/platform/stores/user'
import type { DesktopWindowSnapshot } from './desktop-session-storage'
import { buildRestoreWindowList } from './desktop-session-restore'

const windows = reactive<WindowState[]>([])
let nextZIndex = 100
let nextId = 1
const 桌面容器尺寸 = reactive({ width: window.innerWidth, height: window.innerHeight })

function 生成id(): string { return `win_${Date.now()}_${nextId++}` }

function 生成层级(): number { return nextZIndex++ }

const 任务栏项 = ref<TaskbarItem[]>([])
watch(() => windows.map(w => ({
  id: w.id, title: w.title, icon: w.icon,
  isActive: w.isActive, minimized: w.minimized,
})), (v) => { 任务栏项.value = v }, { immediate: true, deep: true })

function 打开窗口(应用标识: string, 负载?: unknown): string | null {
  const 应用 = getApp(应用标识)
  if (!应用) return null
  const store = useUserStore()
  const 当前角色 = store.用户信息?.role?.toLowerCase()
  if (应用.allowedRoles && 当前角色 && !应用.allowedRoles.includes(当前角色)) {
    console.warn(`打开窗口被拒绝：角色 ${当前角色} 无权访问应用 ${应用标识}`)
    return null
  }

  if (应用.windowType === '后台服务') {
    const 已有服务 = windows.find(w => w.appKey === 应用标识)
    if (已有服务) { 激活窗口(已有服务.id); return 已有服务.id }
    console.warn(`后台服务 ${应用标识} 不支持窗口模式`)
    return null
  }

  if (!应用.allowMultiple) {
    const 已存在 = windows.find(w => w.appKey === 应用标识)
    if (已存在) { 激活窗口(已存在.id); 已存在.minimized = false; return 已存在.id }
  }

  const 偏移 = (windows.length % 10) * 30
  const id = 生成id()

  windows.push({
    id, appKey: 应用标识,
    title: 应用.appName, icon: 应用.icon,
    x: 应用.defaultWidth > 800 ? 120 + 偏移 : 160 + 偏移,
    y: 110 + 偏移,
    width: 应用.defaultWidth, height: 应用.defaultHeight,
    zIndex: nextZIndex++,
    minimized: false, maximized: false, isActive: true,
     windowType: 应用.windowType || '普通窗口',
     payload: (负载 ?? {}) as Record<string, unknown>,
  })

  windows.forEach(w => { if (w.id !== id) w.isActive = false })
  return id
}

function 关闭窗口(id: string) {
  const idx = windows.findIndex(w => w.id === id)
  if (idx === -1) return
  windows.splice(idx, 1)
}

function 切换最小化(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  w.minimized = !w.minimized
  if (w.minimized) {
    w.isActive = false
    const next = [...windows].reverse().find(x => !x.minimized)
    if (next) { next.isActive = true }
  } else { 激活窗口(id) }
}

function 切换最大化(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  if (w.maximized) {
    if (w.preMaximizeState) { w.x = w.preMaximizeState.x; w.y = w.preMaximizeState.y; w.width = w.preMaximizeState.width; w.height = w.preMaximizeState.height }
    w.maximized = false
  } else {
    w.preMaximizeState = { x: w.x, y: w.y, width: w.width, height: w.height }
    w.x = 0; w.y = 0
    w.width = 桌面容器尺寸.width
    w.height = 桌面容器尺寸.height - 48
    w.maximized = true
  }
}

function 激活窗口(id: string) {
  const w = windows.find(x => x.id === id)
  if (!w) return
  windows.forEach(x => x.isActive = false)
  w.isActive = true; w.zIndex = nextZIndex++; w.minimized = false
}

function 设置容器尺寸(width: number, height: number) {
  桌面容器尺寸.width = width
  桌面容器尺寸.height = height
}

function 更新窗口位置(id: string, x: number, y: number) {
  const w = windows.find(win => win.id === id)
  if (!w || w.maximized) return
  w.x = x
  w.y = y
}

function 更新窗口尺寸(id: string, width: number, height: number) {
  const w = windows.find(win => win.id === id)
  if (w && !w.maximized) { w.width = width; w.height = height }
}

function 更新窗口几何(id: string, x: number, y: number, width: number, height: number) {
  const w = windows.find(win => win.id === id)
  if (w && !w.maximized) { w.x = x; w.y = y; w.width = width; w.height = height }
}

function 恢复窗口(快照: DesktopWindowSnapshot[], 当前角色?: string) {
  const 恢复的窗口 = buildRestoreWindowList({
    快照, 当前角色,
    容器宽: 桌面容器尺寸.width,
    容器高: 桌面容器尺寸.height,
    生成id, 生成层级,
  })
  for (const w of 恢复的窗口) {
    const 已存在 = windows.find(x => x.appKey === w.appKey && x.minimized === w.minimized)
    if (已存在) { 激活窗口(已存在.id); continue }
    windows.push(w)
  }
}

export function use窗口管理器() {
  return {
    windows,
    已打开窗口数: computed(() => windows.length),
    任务栏项,
    打开窗口, 关闭窗口, 切换最小化, 切换最大化, 激活窗口,
    更新窗口位置, 更新窗口尺寸, 更新窗口几何,
    设置容器尺寸, 恢复窗口,
  }
}

export const 窗口管理器 = {
  windows,
  get 已打开窗口数() { return windows.length },
  任务栏项,
  打开窗口, 关闭窗口, 切换最小化, 切换最大化, 激活窗口,
  更新窗口位置, 更新窗口尺寸, 更新窗口几何,
  设置容器尺寸, 恢复窗口,
}
