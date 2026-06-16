import { ref, onMounted, onUnmounted } from 'vue'
import { 构建桌面壳图标菜单 as 构建桌面壳图标菜单基础, 构建桌面壳空白菜单 as 构建桌面壳空白菜单基础 } from './desktop-shell-context-menu'
import { 构建文件菜单 as 构建文件菜单基础, 构建文件夹菜单 as 构建文件夹菜单基础, 构建桌面空白菜单 as 构建桌面空白菜单基础, 构建文件夹树节点菜单 as 构建文件夹树节点菜单基础, 构建回收站菜单 as 构建回收站菜单基础, 构建回收站项菜单 as 构建回收站项菜单基础 } from './file-context-menu'

export interface MenuItemConfig {
  键: string
  标签: string
  图标?: string
  禁用?: boolean
  危险?: boolean
  分隔符?: boolean
  子项?: MenuItemConfig[]
}

export type MenuContext = {
  类型: '桌面空白' | '文件' | '文件夹' | '回收站' | '多选' | '桌面壳空白' | '桌面壳图标'
  目标?: Record<string, unknown>
}

let 右键实例序号 = 0

export function use右键菜单() {
  const 实例标识 = `context-menu-${++右键实例序号}`
  const 显示 = ref(false)
  const X = ref(0)
  const Y = ref(0)
  const 当前项 = ref<MenuItemConfig[]>([])
  const 活跃子菜单 = ref<{ 父键: string; 项: MenuItemConfig[]; X: number; Y: number } | null>(null)
  const 上下文 = ref<MenuContext | null>(null)
  let 子菜单关闭计时: number | null = null

  function 获取菜单尺寸(项: MenuItemConfig[]) {
    const 分隔数量 = 项.filter(i => i.分隔符).length
    const 行数量 = 项.filter(i => !i.分隔符).length
    return { 宽: 196, 高: 行数量 * 31 + 分隔数量 * 9 + 12 }
  }

  function 校正边界(ex: number, ey: number, w: number, h: number) {
    const vw = window.innerWidth
    const vh = window.innerHeight
    return {
      x: ex + w > vw ? Math.max(8, vw - w - 8) : ex,
      y: ey + h > vh ? Math.max(8, vh - h - 8) : ey,
    }
  }

  function 打开(e: MouseEvent, 项: MenuItemConfig[], ctx: MenuContext) {
    e.preventDefault()
    e.stopPropagation()
    document.dispatchEvent(new CustomEvent('desktop:context-menu-open', { detail: 实例标识 }))
    当前项.value = 项
    上下文.value = ctx
    活跃子菜单.value = null
    const 尺寸 = 获取菜单尺寸(项)
    const pos = 校正边界(e.clientX, e.clientY, 尺寸.宽, 尺寸.高)
    X.value = pos.x
    Y.value = pos.y
    显示.value = true
  }

  function 关闭() {
    显示.value = false
    当前项.value = []
    活跃子菜单.value = null
    上下文.value = null
    清理子菜单关闭计时()
  }

  function 展开子菜单(e: MouseEvent, 父键: string, 项: MenuItemConfig[]) {
    e.stopPropagation()
    清理子菜单关闭计时()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const 尺寸 = 获取菜单尺寸(项)
    const pos = 校正边界(rect.right + 6, rect.top - 4, 尺寸.宽, 尺寸.高)
    活跃子菜单.value = { 父键, 项, X: pos.x, Y: pos.y }
  }

  function 清理子菜单关闭计时() {
    if (子菜单关闭计时 !== null) window.clearTimeout(子菜单关闭计时)
    子菜单关闭计时 = null
  }

  function 计划关闭子菜单() {
    清理子菜单关闭计时()
    子菜单关闭计时 = window.setTimeout(() => {
      活跃子菜单.value = null
      子菜单关闭计时 = null
    }, 260)
  }

  function 关闭子菜单() { 计划关闭子菜单() }
  function 保持子菜单展开() { 清理子菜单关闭计时() }

  function 分隔项(): MenuItemConfig[] {
    return [{ 键: '_sep', 标签: '', 分隔符: true }]
  }

  function 构建文件菜单(可写: boolean): MenuItemConfig[] { return 构建文件菜单基础(可写, 分隔项) }
  function 构建文件夹菜单(可写: boolean): MenuItemConfig[] { return 构建文件夹菜单基础(可写, 分隔项) }
  function 构建桌面空白菜单(可写: boolean): MenuItemConfig[] { return 构建桌面空白菜单基础(可写, 分隔项) }
  function 构建文件夹树节点菜单(可写: boolean): MenuItemConfig[] { return 构建文件夹树节点菜单基础(可写, 分隔项) }
  function 构建回收站菜单(可写?: boolean): MenuItemConfig[] { return 构建回收站菜单基础(可写, 分隔项) }
  function 构建回收站项菜单(可写: boolean): MenuItemConfig[] { return 构建回收站项菜单基础(可写) }

  function 构建桌面壳空白菜单(): MenuItemConfig[] {
    return 构建桌面壳空白菜单基础(分隔项)
  }

  function 构建桌面壳图标菜单(应用标识: string, 可写?: boolean): MenuItemConfig[] {
    return 构建桌面壳图标菜单基础(应用标识, 可写, 分隔项, 构建回收站菜单)
  }

  const 处理其他菜单打开 = (事件: Event) => {
    if ((事件 as CustomEvent<string>).detail !== 实例标识) 关闭()
  }
  const 处理按键 = (事件: KeyboardEvent) => {
    if (事件.key === 'Escape' && 显示.value) 关闭()
  }

  onMounted(() => {
    document.addEventListener('click', 关闭)
    document.addEventListener('keydown', 处理按键)
    document.addEventListener('desktop:context-menu-open', 处理其他菜单打开)
  })

  onUnmounted(() => {
    document.removeEventListener('click', 关闭)
    document.removeEventListener('keydown', 处理按键)
    document.removeEventListener('desktop:context-menu-open', 处理其他菜单打开)
  })

  return {
    显示, X, Y, 当前项, 活跃子菜单, 上下文,
    打开, 关闭, 展开子菜单, 关闭子菜单, 保持子菜单展开,
    构建文件菜单, 构建文件夹菜单, 构建桌面空白菜单,
    构建文件夹树节点菜单, 构建回收站菜单, 构建回收站项菜单,
    构建桌面壳空白菜单, 构建桌面壳图标菜单,
  }
}
