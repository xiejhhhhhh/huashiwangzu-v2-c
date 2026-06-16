import { computed } from 'vue'
import { useUserStore } from '@/platform/stores/user'

/** 角色等级：数字越大权限越高 */
const 角色等级: Record<string, number> = {
  viewer: 1,
  editor: 2,
  admin: 9,
}

/** 各角色可见菜单名称列表（顺序即显示顺序） */
const 角色菜单映射: Record<string, string[]> = {
  viewer: ['桌面', '知识库', 'AI 助手', '我的任务'],
  editor: ['桌面', '知识库', 'AI 助手', '我的任务'],
  admin: ['仪表盘', 'AI 助手', '桌面', '知识库', '设置', '我的任务'],
}

export function use权限() {
  const store = useUserStore()

  /** 当前用户角色，默认为 viewer */
  const 当前角色 = computed(() => store.用户信息?.role || 'viewer')

  /** 是否为管理员 */
  const 是管理员 = computed(() => 当前角色.value === 'admin')

  /** 是否为编辑者及以上（editor / admin） */
  const 是编辑者及以上 = computed(() => {
    const 角色 = 当前角色.value
    return 角色 === 'admin' || 角色 === 'editor'
  })

  /** 判断当前角色是否至少达到指定角色等级 */
  function 角色至少为(最低角色: string): boolean {
    const 当前等级 = 角色等级[当前角色.value] ?? 0
    const 要求等级 = 角色等级[最低角色] ?? 0
    return 当前等级 >= 要求等级
  }

  /** 判断菜单项对当前角色是否可见 */
  function 可访问菜单(菜单项: { 名称: string }): boolean {
    const 可见菜单 = 角色菜单映射[当前角色.value] ?? 角色菜单映射.viewer
    return 可见菜单.includes(菜单项.名称)
  }

  /**
   * 可执行的操作分类（用于按钮级别控制）
   */
  const 写操作集合 = new Set([
    '桌面_新建文件夹', '桌面_上传', '桌面_重命名', '桌面_删除',
    '桌面_回收站还原', '桌面_彻底删除', '桌面_清空回收站',
    '知识库_编辑编目', '知识库_触发分析',
    'Agent_删除会话',
    '后台任务_重试', '后台任务_取消',
  ])
  const 管理操作集合 = new Set([
    '设置_用户创建', '设置_用户编辑', '设置_用户禁用',
    '设置_系统配置保存', '设置_角色矩阵保存',
  ])

  /**
   * 判断当前角色是否能执行指定操作
   */
  function 可执行操作(操作: string): boolean {
    const 角色 = 当前角色.value
    if (角色 === 'admin') return true
    if (角色 === 'editor') return !管理操作集合.has(操作)
    if (角色 === 'viewer') return false
    return false
  }

  /** 判断当前角色能否预览文件：viewer 及以上均可 */
  function 可预览文件(_文件对象?: unknown): boolean {
    return 角色至少为('viewer')
  }

  return {
    当前角色,
    是管理员,
    是编辑者及以上,
    角色至少为,
    可访问菜单,
    可执行操作,
    可预览文件,
  }
}
