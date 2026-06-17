import { computed } from 'vue'
import { useUserStore } from '@/platform/stores/user'
import type { MenuItem } from '@/shared/api/types'

const roleLevels: Record<string, number> = {
  viewer: 1,
  editor: 2,
  admin: 9,
}

const roleMenuMap: Record<string, string[]> = {
  viewer: ['desktop', 'tasks'],
  editor: ['desktop', 'tasks'],
  admin: ['dashboard', 'desktop', 'settings', 'tasks'],
}

export function usePermission() {
  const store = useUserStore()

  const currentRole = computed(() => store.userInfo?.role || 'viewer')

  const isAdmin = computed(() => currentRole.value === 'admin')

  const isEditorOrAbove = computed(() => {
    const role = currentRole.value
    return role === 'admin' || role === 'editor'
  })

  function hasMinRole(minRole: string): boolean {
    const currentLevel = roleLevels[currentRole.value] ?? 0
    const requiredLevel = roleLevels[minRole] ?? 0
    return currentLevel >= requiredLevel
  }

  function canAccessMenu(menuItem: MenuItem): boolean {
    const visibleMenus = roleMenuMap[currentRole.value] ?? roleMenuMap.viewer
    return visibleMenus.includes(menuItem.path.replace(/^\//, '') || menuItem.name)
  }

  const writeActions = new Set([
    'desktop:create-folder', 'desktop:upload', 'desktop:rename', 'desktop:delete',
    'desktop:restore-recycle-bin', 'desktop:delete-permanently', 'desktop:empty-recycle-bin',
    'task:retry', 'task:cancel',
  ])
  const adminActions = new Set([
    'settings:create-user', 'settings:edit-user', 'settings:disable-user',
    'settings:save-system-config', 'settings:save-role-matrix',
  ])

  function canExecuteAction(action: string): boolean {
    const role = currentRole.value
    if (role === 'admin') return true
    if (role === 'editor') return writeActions.has(action) && !adminActions.has(action)
    if (role === 'viewer') return false
    return false
  }

  function canPreviewFile(_file?: unknown): boolean {
    return hasMinRole('viewer')
  }

  return {
    currentRole,
    isAdmin,
    isEditorOrAbove,
    hasMinRole,
    canAccessMenu,
    canExecuteAction,
    canPreviewFile,
  }
}
