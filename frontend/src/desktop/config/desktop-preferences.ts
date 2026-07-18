/**
 * 桌面配置系统 - 所有桌面视觉/行为参数的唯一真相来源
 *
 * 设计原则：
 * 1. 所有硬编码数值集中到这里
 * 2. 用户偏好存 localStorage + 后端同步
 * 3. 运行时响应式，改配置立即生效
 * 4. 其他模块通过 useDesktopConfig() 读取，不直接写常量
 */
import { reactive, computed, watch } from 'vue'
import { desktopStateStore, scheduleDesktopStateSave } from '@/desktop/window-manager/desktop-state-store'
import {
  applyDesktopSkin,
  getActiveDesktopSkinMetrics,
  isDesktopShellSkinId,
  readStoredDesktopSkin,
  persistDesktopSkin,
  type DesktopShellSkinId,
} from '@/desktop/skins'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

export type IconSize = 'small' | 'medium' | 'large'
export type TaskbarPosition = 'bottom' | 'top'
export type IconLayout = 'auto-arrange' | 'free'
export type LauncherStyle = 'center-panel' | 'left-panel'
export type { DesktopShellSkinId }

export interface DesktopConfig {
  // 图标系统
  iconSize: IconSize
  iconLayout: IconLayout
  iconGridGap: number
  showIconLabels: boolean

  // 任务栏
  taskbarPosition: TaskbarPosition
  taskbarHeight: number
  taskbarShowClock: boolean
  taskbarShowDate: boolean
  taskbarGroupWindows: boolean

  // 窗口
  windowAnimationDuration: number
  windowSnapThreshold: number
  windowMinWidth: number
  windowMinHeight: number

  // 启动器
  launcherStyle: LauncherStyle
  launcherWidth: number

  // 壁纸
  wallpaperType: 'gradient' | 'image' | 'color'
  wallpaperValue: string

  // 反馈
  enableMicroAnimations: boolean
  enableOperationToast: boolean

  /**
   * Desktop hotkeys (Web-safe).
   * Default false: never steal browser/OS shortcuts.
   * When true, only non-conflicting or explicitly allowed combos are handled,
   * and only when focus is not in an editable field.
   */
  enableDesktopHotkeys: boolean

  /** Shell visual skin: macos | win11 (behavior runtime stays shared). */
  shellSkin: DesktopShellSkinId
}

// ═══════════════════════════════════════════════════
// 图标尺寸映射
// ═══════════════════════════════════════════════════

export const ICON_SIZE_MAP: Record<IconSize, { width: number; height: number; imageSize: number; fontSize: number }> = {
  small:  { width: 68, height: 72, imageSize: 36, fontSize: 10 },
  medium: { width: 88, height: 92, imageSize: 48, fontSize: 11 },
  large:  { width: 108, height: 112, imageSize: 64, fontSize: 12 },
}

// ═══════════════════════════════════════════════════
// 默认配置
// ═══════════════════════════════════════════════════

const DEFAULT_CONFIG: DesktopConfig = {
  iconSize: 'medium',
  iconLayout: 'auto-arrange',
  iconGridGap: 4,
  showIconLabels: true,

  taskbarPosition: 'bottom',
  taskbarHeight: 66,
  taskbarShowClock: false,
  taskbarShowDate: false,
  taskbarGroupWindows: true,

  windowAnimationDuration: 280,
  windowSnapThreshold: 28,
  windowMinWidth: 400,
  windowMinHeight: 260,

  launcherStyle: 'center-panel',
  launcherWidth: 520,

  wallpaperType: 'gradient',
  wallpaperValue: 'linear-gradient(135deg, #0f172a 0%, #1d4ed8 50%, #7c3aed 100%)',

  enableMicroAnimations: true,
  enableOperationToast: true,

  enableDesktopHotkeys: false,

  shellSkin: 'macos',
}

// ═══════════════════════════════════════════════════
// 响应式配置实例
// ═══════════════════════════════════════════════════

const config = reactive<DesktopConfig>({ ...DEFAULT_CONFIG, shellSkin: readStoredDesktopSkin() })

// 从 desktopStateStore 恢复偏好
function loadConfigFromState(): void {
  const saved = desktopStateStore.state.appState?.['__desktop_config__'] as Partial<DesktopConfig> | undefined
  if (saved) {
    Object.entries(saved).forEach(([key, value]) => {
      if (key in config && value !== undefined) {
        ;(config as Record<string, unknown>)[key] = value
      }
    })
  }
  if (!isDesktopShellSkinId(config.shellSkin)) config.shellSkin = readStoredDesktopSkin()
  // taskbar height always follows active skin metrics (not free-form stale values)
  config.taskbarHeight = getActiveDesktopSkinMetrics().dockHeight
}

// 持久化到 desktopStateStore
function saveConfigToState(): void {
  if (!desktopStateStore.state.appState) desktopStateStore.state.appState = {}
  desktopStateStore.state.appState['__desktop_config__'] = JSON.parse(JSON.stringify(config))
  scheduleDesktopStateSave()
}

// 监听变化自动保存
let watchInitialized = false
function ensureWatch(): void {
  if (watchInitialized) return
  watchInitialized = true
  watch(() => ({ ...config }), () => {
    saveConfigToState()
  }, { deep: true })
}

// ═══════════════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════════════

const iconMetrics = computed(() => {
  const size = ICON_SIZE_MAP[config.iconSize]
  const gap = config.iconGridGap
  return {
    ...size,
    stepX: size.width + gap,
    stepY: size.height + gap,
  }
})

const taskbarReservedHeight = computed(() => {
  const metrics = getActiveDesktopSkinMetrics()
  return metrics.dockHeight + metrics.dockBottomGap
})

function syncShellSkin(host?: HTMLElement | null): void {
  const skin = applyDesktopSkin(config.shellSkin, host)
  config.taskbarHeight = skin.metrics.dockHeight
  persistDesktopSkin(skin.id)
}

// ═══════════════════════════════════════════════════
// 公共接口
// ═══════════════════════════════════════════════════

export function useDesktopConfig() {
  loadConfigFromState()
  ensureWatch()

  return {
    config,
    iconMetrics,
    taskbarReservedHeight,

    /** 批量更新配置项 */
    updateConfig(partial: Partial<DesktopConfig>): void {
      Object.entries(partial).forEach(([key, value]) => {
        if (key in config) {
          ;(config as Record<string, unknown>)[key] = value
        }
      })
      if (partial.shellSkin && isDesktopShellSkinId(partial.shellSkin)) {
        syncShellSkin(document.querySelector('.desktop-shell-container') as HTMLElement | null)
      }
    },

    /** Switch shell visual skin (macos | win11). Runtime behavior stays shared. */
    setShellSkin(skin: DesktopShellSkinId, host?: HTMLElement | null): void {
      if (!isDesktopShellSkinId(skin)) return
      config.shellSkin = skin
      syncShellSkin(host ?? (document.querySelector('.desktop-shell-container') as HTMLElement | null))
    },

    /** Apply current skin tokens to a host element (call on shell mount). */
    applyCurrentShellSkin(host?: HTMLElement | null): void {
      syncShellSkin(host)
    },

    /** 重置为默认 */
    resetConfig(): void {
      Object.assign(config, { ...DEFAULT_CONFIG, shellSkin: readStoredDesktopSkin() })
      syncShellSkin(document.querySelector('.desktop-shell-container') as HTMLElement | null)
    },

    /** 获取图标尺寸数据 */
    getIconSizeData(size?: IconSize) {
      return ICON_SIZE_MAP[size || config.iconSize]
    },
  }
}

export { config as desktopConfig }
