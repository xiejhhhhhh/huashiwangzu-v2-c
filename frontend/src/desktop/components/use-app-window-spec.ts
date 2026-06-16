import { ref, computed } from 'vue'

export interface AppWindowSpecOptions {
  sidebarCollapsed?: boolean
  sidebarWidth?: number
  drawerVisible?: boolean
  layout?: 'management' | 'editor' | 'chat' | 'search' | 'file-manager' | 'dashboard'
}

export function use应用窗口规范(options: AppWindowSpecOptions = {}) {
  const sidebarCollapsed = ref(options.sidebarCollapsed ?? false)
  const sidebarWidth = ref(options.sidebarWidth ?? 260)
  const drawerVisible = ref(options.drawerVisible ?? false)
  const layout = ref(options.layout ?? 'management')

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setSidebarCollapsed(v: boolean) {
    sidebarCollapsed.value = v
  }

  function openDrawer() {
    drawerVisible.value = true
  }

  function closeDrawer() {
    drawerVisible.value = false
  }

  function toggleDrawer() {
    drawerVisible.value = !drawerVisible.value
  }

  const sidebarStyle = computed(() => ({
    width: sidebarCollapsed.value ? '0px' : `${sidebarWidth.value}px`,
  }))

  const contentStyle = computed(() => {
    if (layout.value === 'chat') {
      return { padding: '0', background: 'transparent' }
    }
    if (layout.value === 'editor') {
      return { padding: '0' }
    }
    return {}
  })

  return {
    sidebarCollapsed,
    sidebarWidth,
    drawerVisible,
    layout,
    toggleSidebar,
    setSidebarCollapsed,
    openDrawer,
    closeDrawer,
    toggleDrawer,
    sidebarStyle,
    contentStyle,
  }
}
