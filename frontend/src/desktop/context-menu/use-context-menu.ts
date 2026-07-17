import { ref, onMounted, onUnmounted } from 'vue'
import { buildDesktopShellIconMenu, buildDesktopShellBlankMenu } from './desktop-shell-context-menu'
import { buildFileMenu, buildFolderMenu, buildDesktopBlankMenu, buildFolderTreeNodeMenu, buildRecycleBinMenu, buildRecycleBinItemMenu } from './file-context-menu'

export interface MenuItemConfig {
  key: string
  label: string
  icon?: string
  disabled?: boolean
  danger?: boolean
  separator?: boolean
  children?: MenuItemConfig[]
}

export type MenuContext = {
  type: 'desktop-blank' | 'file' | 'folder' | 'recycle-bin' | 'recycle-bin-item' | 'multi-select' | 'desktop-shell-blank' | 'desktop-shell-icon'
  target?: Record<string, unknown>
}

let contextMenuInstanceSeq = 0

export function useContextMenu() {
  const instanceId = `context-menu-${++contextMenuInstanceSeq}`
  const visible = ref(false)
  const x = ref(0)
  const y = ref(0)
  const currentItems = ref<MenuItemConfig[]>([])
  const activeSubmenu = ref<{ parentKey: string; items: MenuItemConfig[]; x: number; y: number } | null>(null)
  const context = ref<MenuContext | null>(null)
  let submenuCloseTimer: number | null = null
  let returnFocus: HTMLElement | null = null

  function getMenuSize(items: MenuItemConfig[]) {
    const separatorCount = items.filter(i => i.separator).length
    const rowCount = items.filter(i => !i.separator).length
    return { width: 196, height: rowCount * 31 + separatorCount * 9 + 12 }
  }

  function clampToViewport(ex: number, ey: number, w: number, h: number) {
    const vw = window.innerWidth
    const vh = window.innerHeight
    return {
      x: ex + w > vw ? Math.max(8, vw - w - 8) : ex,
      y: ey + h > vh ? Math.max(8, vh - h - 8) : ey,
    }
  }

  function open(e: MouseEvent, items: MenuItemConfig[], ctx: MenuContext) {
    e.preventDefault()
    e.stopPropagation()
    document.dispatchEvent(new CustomEvent('desktop:context-menu-open', { detail: instanceId }))
    currentItems.value = items
    context.value = ctx
    activeSubmenu.value = null
    returnFocus = e.currentTarget instanceof HTMLElement
      ? e.currentTarget
      : document.activeElement instanceof HTMLElement ? document.activeElement : null
    const size = getMenuSize(items)
    const pos = clampToViewport(e.clientX, e.clientY, size.width, size.height)
    x.value = pos.x
    y.value = pos.y
    visible.value = true
  }

  function close() {
    const wasVisible = visible.value
    const target = returnFocus
    visible.value = false
    currentItems.value = []
    activeSubmenu.value = null
    context.value = null
    clearSubmenuCloseTimer()
    returnFocus = null
    if (wasVisible && target?.isConnected) requestAnimationFrame(() => target.focus())
  }

  function openSubmenu(e: MouseEvent, parentKey: string, items: MenuItemConfig[]) {
    e.stopPropagation()
    clearSubmenuCloseTimer()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const size = getMenuSize(items)
    const pos = clampToViewport(rect.right + 6, rect.top - 4, size.width, size.height)
    activeSubmenu.value = { parentKey, items, x: pos.x, y: pos.y }
  }

  function clearSubmenuCloseTimer() {
    if (submenuCloseTimer !== null) window.clearTimeout(submenuCloseTimer)
    submenuCloseTimer = null
  }

  function scheduleCloseSubmenu() {
    clearSubmenuCloseTimer()
    submenuCloseTimer = window.setTimeout(() => {
      activeSubmenu.value = null
      submenuCloseTimer = null
    }, 260)
  }

  function closeSubmenu() { scheduleCloseSubmenu() }
  function keepSubmenuOpen() { clearSubmenuCloseTimer() }

  function separatorItems(): MenuItemConfig[] {
    return [{ key: '_sep', label: '', separator: true }]
  }

  function createFileMenu(writable: boolean): MenuItemConfig[] { return buildFileMenu(writable, separatorItems) }
  function createFolderMenu(writable: boolean): MenuItemConfig[] { return buildFolderMenu(writable, separatorItems) }
  function createDesktopBlankMenu(writable: boolean): MenuItemConfig[] { return buildDesktopBlankMenu(writable, separatorItems) }
  function createFolderTreeNodeMenu(writable: boolean): MenuItemConfig[] { return buildFolderTreeNodeMenu(writable, separatorItems) }
  function createRecycleBinMenu(writable?: boolean): MenuItemConfig[] { return buildRecycleBinMenu(writable, separatorItems) }
  function createRecycleBinItemMenu(writable: boolean): MenuItemConfig[] { return buildRecycleBinItemMenu(writable) }

  function createDesktopShellBlankMenu(): MenuItemConfig[] {
    return buildDesktopShellBlankMenu(separatorItems)
  }

  function createDesktopShellIconMenu(appKey: string, writable?: boolean): MenuItemConfig[] {
    return buildDesktopShellIconMenu(appKey, writable, separatorItems, createRecycleBinMenu)
  }

  const handleOtherMenuOpen = (event: Event) => {
    if ((event as CustomEvent<string>).detail !== instanceId) close()
  }
  const handleKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && visible.value) close()
  }

  onMounted(() => {
    document.addEventListener('click', close)
    document.addEventListener('keydown', handleKeydown)
    document.addEventListener('desktop:context-menu-open', handleOtherMenuOpen)
  })

  onUnmounted(() => {
    document.removeEventListener('click', close)
    document.removeEventListener('keydown', handleKeydown)
    document.removeEventListener('desktop:context-menu-open', handleOtherMenuOpen)
  })

  return {
    visible, x, y, currentItems, activeSubmenu, context,
    open, close, openSubmenu, closeSubmenu, keepSubmenuOpen,
    createFileMenu, createFolderMenu, createDesktopBlankMenu,
    createFolderTreeNodeMenu, createRecycleBinMenu, createRecycleBinItemMenu,
    createDesktopShellBlankMenu, createDesktopShellIconMenu,
  }
}
