import { computed, reactive } from 'vue'
import { useUserStore } from '@/platform/stores/user'
import api from '@/shared/api/index'

const 角色等级: Record<string, number> = {
  viewer: 1,
  editor: 2,
  admin: 9,
}

interface 权限定义 {
  最低角色: string
  模块: string
}

interface 权限矩阵项 {
  action: string
  名称: string
  模块: string
  最低角色: string
}

const 权限注册表 = reactive(new Map<string, 权限定义>())
let 已加载 = false
let 加载中 = false
let 加载Promise: Promise<void> | null = null

/**
 * 从后端加载权限声明并填充注册表
 */
async function 加载所有权限从后端(): Promise<void> {
  if (已加载) return
  if (加载中 && 加载Promise) {
    return 加载Promise
  }
  if (加载中) return

  加载中 = true
  加载Promise = (async () => {
    try {
      const 响应: any = await api.get('/roles/matrix')
      const 矩阵 = 响应?.data?.matrix || []
      const 列表: 权限矩阵项[] = 矩阵.flatMap((角色: any) =>
        Object.entries(角色.permissions || {})
          .filter(([, enabled]) => enabled)
          .map(([action]) => ({
            action,
            名称: action,
            模块: 'system',
            最低角色: 角色.role_key,
          }))
      )
      权限注册表.clear()
      for (const 项 of 列表) {
        权限注册表.set(项.action, { 最低角色: 项.最低角色, 模块: 项.模块 })
      }
      已加载 = true
    } catch {
      // 加载失败时保留空注册表
      console.warn('[权限] 加载权限声明失败，权限检查将默认拒绝')
    } finally {
      加载中 = false
    }
  })()

  return 加载Promise
}

/**
 * 静态检查：根据当前角色判断是否有权限执行指定操作
 */
export async function checkPermissionAction(操作: string): Promise<boolean> {
  const 用户Store = useUserStore()
  const 角色 = 用户Store.用户信息?.role || 'viewer'
  if (角色 === 'admin') return true

  await 加载所有权限从后端()

  const 定义 = 权限注册表.get(操作)
  if (!定义) return false
  return (角色等级[角色] ?? 0) >= (角色等级[定义.最低角色] ?? 0)
}

/**
 * 响应式权限 Action 组合函数
 */
export function use权限Action() {
  const store = useUserStore()
  const 当前角色 = computed(() => store.用户信息?.role || 'viewer')

  async function 可执行(操作: string): Promise<boolean> {
    if (当前角色.value === 'admin') return true

    await 加载所有权限从后端()

    const 定义 = 权限注册表.get(操作)
    if (!定义) return false
    return (角色等级[当前角色.value] ?? 0) >= (角色等级[定义.最低角色] ?? 0)
  }

  return { 可执行, 当前角色 }
}
