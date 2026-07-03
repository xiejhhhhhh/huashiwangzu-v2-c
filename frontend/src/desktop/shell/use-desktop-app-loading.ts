import { ref, onMounted, onUnmounted } from 'vue'
import { loadAppRegistry } from '@/desktop/app-registry/app-loader'
import { useWindowManager } from '@/desktop/window-manager/window-manager'
import { loadDesktopState } from '@/desktop/window-manager/desktop-state-store'
import { createWindowStateSync } from '@/desktop/window-manager/window-state-sync'
import { restorePersistedIconPositions } from '@/desktop/drag-drop/drag-tool'
import { useUserStore } from '@/platform/stores/user'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import type { Ref } from 'vue'

export function useDesktopAppLoading(currentRole: Ref<string>) {
  const windowMgr = useWindowManager()
  const userStore = useUserStore()
  const allAppList = ref<AppRegistryEntry[]>([])
  const desktopAppList = ref<AppRegistryEntry[]>([])
  const launcherAppList = ref<AppRegistryEntry[]>([])
  const sidebarAppList = ref<AppRegistryEntry[]>([])
  const trayAppList = ref<AppRegistryEntry[]>([])
  const registryError = ref<string | null>(null)
  const loading = ref(true)
  const desktopContainerRef = ref<HTMLElement | null>(null)
  let resizeObserver: ResizeObserver | null = null

  function runtimePermissions(role?: string): string[] {
    if (role === 'admin') return ['viewer', 'editor', 'admin']
    if (role === 'editor') return ['viewer', 'editor']
    return ['viewer']
  }

  const windowSync = createWindowStateSync(windowMgr.windows)

  function updateContainerSize() {
    if (desktopContainerRef.value) windowMgr.setContainerSize(desktopContainerRef.value.clientWidth, desktopContainerRef.value.clientHeight)
    requestAnimationFrame(() => restorePersistedIconPositions())
  }

  async function loadAppRegistryData() {
    registryError.value = null
    loading.value = true
    try {
      const allApps = await loadAppRegistry(currentRole.value)
      allAppList.value = allApps
      desktopAppList.value = allApps.filter(a => a.showOnDesktop)
      launcherAppList.value = allApps.filter(a => a.showInLauncher)
      sidebarAppList.value = allApps.filter(a => a.showInSidebar)
      trayAppList.value = allApps.filter(a => a.showInTray)

      // 给模块 runtime 注入框架上下文（当前用户权限等）
      ;(window as unknown as { __HUASHI_RUNTIME__?: unknown }).__HUASHI_RUNTIME__ = {
        mode: 'framework',
        api_base_url: '/api',
        permissions: runtimePermissions(userStore.userInfo?.role),
        module_settings: {},
      }

      if (userStore.userInfo?.id) {
        const desktopState = await loadDesktopState()
        windowMgr.restoreWindows(desktopState.windows, currentRole.value)
      }

      updateContainerSize()
      resizeObserver = new ResizeObserver(updateContainerSize)
      if (desktopContainerRef.value) resizeObserver.observe(desktopContainerRef.value)
    } catch (e: unknown) {
      registryError.value = (e as {message?: string})?.message || '桌面应用清单加载失败，请联系管理员'
    } finally {
      loading.value = false
      if (import.meta.env.DEV) {
        const { useDesktopAppHandleV2 } = await import('@/desktop/app-registry/desktop-app-handle-v2')
        const handleV2 = useDesktopAppHandleV2()
        ;(window as { __test__?: unknown }).__test__ = { handleV2 }
      }
    }
  }

  function retryLoadRegistry() { loadAppRegistryData() }

  onMounted(loadAppRegistryData)
  onUnmounted(() => {
    windowSync.stopSync()
    resizeObserver?.disconnect()
  })

  return {
    allAppList,
    desktopAppList,
    launcherAppList,
    sidebarAppList,
    trayAppList,
    registryError,
    loading,
    desktopContainerRef,
    retryLoadRegistry,
    updateContainerSize,
  }
}
