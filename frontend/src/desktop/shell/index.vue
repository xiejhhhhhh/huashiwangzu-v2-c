<template>
  <div ref="桌面容器引用" class="桌面壳-容器" @contextmenu.prevent="handleDesktopContextMenu" @mousedown="桌面鼠标按下" @dragover.prevent="桌面拖入" @dragleave.prevent="桌面拖离" @drop.prevent="桌面放下">
    <div class="桌面壳-壁纸" :style="{ backgroundImage: `url(${壁纸})` }" />
    <div class="桌面壳-图标层">
      <component :is="桌面图标网格" :应用列表="桌面应用列表" :文件列表="桌面文件列表" @openApp="handleOpenApp" @openFile="openDesktopEntry" @右键应用="handleAppContextMenu" />
      <SelectionBox />
    </div>
    <component
      :is="桌面窗口框架"
      v-for="w in 管理器.windows"
      :key="w.id"
      :id="w.id"
      :title="w.title"
      :icon="w.icon"
      :x="w.x"
      :y="w.y"
      :width="w.width"
      :height="w.height"
      :z-index="w.zIndex"
      :minimized="w.minimized"
      :maximized="w.maximized"
      :is-active="w.isActive"
      :应用标识="w.appKey"
      :payload="w.payload"
      @激活="管理器.激活窗口"
      @关闭="管理器.关闭窗口"
      @最小化="管理器.切换最小化"
      @最大化="管理器.切换最大化"
      @更新位置="管理器.更新窗口位置"
      @更新几何="管理器.更新窗口几何"
    />
    <component :is="桌面任务栏" :任务栏项="unref(管理器.任务栏项)" :启动器打开="显示启动器" :托盘应用列表="托盘应用列表" @切换窗口="handleSwitchWindow" @打开启动器="显示启动器 = !显示启动器" @打开托盘应用="管理器.打开窗口" />
    <component :is="桌面启动器" v-if="显示启动器" :显示="显示启动器" :应用列表="开始菜单应用列表" @openApp="handleLauncherOpen" @执行命令="处理开始菜单命令" @关闭="显示启动器 = false" />
    <component :is="桌面右侧功能栏" :显示="显示右侧栏" :当前路径="右侧栏路径" :当前应用标识="右侧栏应用标识" :应用列表="右侧功能应用列表" @关闭="显示右侧栏 = false" @切换="openSidebar" @在窗口打开="handleOpenApp" />
    <ContextMenu
      :显示="右键.显示.value"
      :X="右键.X.value"
      :Y="右键.Y.value"
      :上下文类型="右键.上下文.value?.类型"
      :当前项="右键.当前项.value"
      :活跃子菜单="右键.活跃子菜单.value"
      :展开子菜单="右键.展开子菜单"
      :关闭子菜单="右键.关闭子菜单"
      :保持子菜单展开="右键.保持子菜单展开"
      @select="handleContextMenuSelect"
    />
    <div v-if="注册表错误" class="桌面壳-错误">
       <p>{{ 注册表错误 }}</p>
       <button @click="重试加载注册表">重试</button>
     </div>
     <div v-else-if="!管理器.已打开窗口数" class="桌面壳-提示">
       双击图标openApp · 右键继续管理文件与回收站
     </div>
     <div v-if="桌面拖放激活" class="桌面壳-拖放提示">松开后上传到桌面</div>
     <div v-if="加载中" class="桌面壳-加载中">加载中...</div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, computed, unref } from 'vue'
import { use右键菜单 } from '@/desktop/context-menu/use-context-menu'
import ContextMenu from '@/desktop/context-menu/context-menu.vue'
import { use窗口管理器 } from '@/desktop/window-manager/window-manager'
import { getApp } from '@/desktop/app-registry/app-registry'
import { use权限 } from '@/shared/composables/use-permission'
import { useUserStore } from '@/platform/stores/user'
import { use桌面事件总线 } from '@/desktop/events/use-desktop-event-bus'
import SelectionBox from '@/desktop/selection/SelectionBox.vue'
import { useDesktopShellDropUpload } from './use-desktop-shell-drop-upload'
import { useDesktopRootFiles } from './use-desktop-root-files'
import { useDesktopAppLoading } from './use-desktop-app-loading'
import { useDesktopPointer } from './use-desktop-pointer'
const 桌面图标网格 = defineAsyncComponent(() => import('@/desktop/shell/desktop-icon-grid.vue'))
const 桌面窗口框架 = defineAsyncComponent(() => import('@/desktop/window-manager/desktop-window-frame.vue'))
const 桌面任务栏 = defineAsyncComponent(() => import('@/desktop/taskbar/desktop-taskbar.vue'))
const 桌面启动器 = defineAsyncComponent(() => import('@/desktop/launcher/desktop-launcher.vue'))
const 桌面右侧功能栏 = defineAsyncComponent(() => import('@/desktop/shell/desktop-right-sidebar.vue'))
const 管理器 = use窗口管理器()
const { 是编辑者及以上: 可业务写, 当前角色 } = use权限()
const 右键 = use右键菜单()
const 用户Store = useUserStore()
const { emit } = use桌面事件总线()
const { 桌面拖放激活, 桌面拖入, 桌面拖离, 桌面放下 } = useDesktopShellDropUpload()
const { 桌面文件列表, openDesktopEntry } = useDesktopRootFiles()
const { 桌面应用列表, 开始菜单应用列表, 右侧功能应用列表, 托盘应用列表, 注册表错误, 加载中, 桌面容器引用, 重试加载注册表, 更新容器尺寸 } = useDesktopAppLoading(当前角色)
const { 桌面鼠标按下 } = useDesktopPointer()

const 显示启动器 = ref(false); const 显示右侧栏 = ref(false); const 右侧栏应用标识 = ref('dashboard')

const 壁纸 = 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0f172a"/><stop offset="50%" stop-color="#1d4ed8"/><stop offset="100%" stop-color="#7c3aed"/></linearGradient><radialGradient id="r" cx="30%" cy="20%" r="60%"><stop offset="0%" stop-color="rgba(191,219,254,0.35)"/><stop offset="100%" stop-color="rgba(15,23,42,0)"/></radialGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><rect width="100%" height="100%" fill="url(#r)"/></svg>')
function handleOpenApp(应用标识: string) { 管理器.打开窗口(应用标识) }
function openSidebar(应用标识 = 'dashboard') { 右侧栏应用标识.value = 应用标识; 显示右侧栏.value = true }
function handleLauncherOpen(应用标识: string) {
  显示启动器.value = false
  const app = getApp(应用标识)
  if (app?.showInSidebar) openSidebar(应用标识); else handleOpenApp(应用标识)
}
async function 处理开始菜单命令(命令: string) {
  const { windows: ws, 切换最小化: toggle } = 管理器
  if (命令 === '打开右栏') openSidebar('dashboard')
  else if (命令 === '退出登录') { await 用户Store.登出(); window.location.href = '/' }
  else if (命令.startsWith('最小化') || 命令.startsWith('还原')) ws.forEach((w: { id: string }) => toggle(w.id))
  显示启动器.value = false
}
function getSidebarPath(应用标识: string): string {
  const app = 右侧功能应用列表.value.find(a => a.appKey === 应用标识)
  return app ? '/' + app.appKey : '/dashboard'
}
const 右侧栏路径 = computed(() => getSidebarPath(右侧栏应用标识.value))
function handleAppContextMenu(应用标识: string, e: MouseEvent) {
  const items = 右键.构建桌面壳图标菜单(应用标识, 可业务写.value)
  if (!items.length) return
  右键.打开(e, items, { 类型: '桌面壳图标', 目标: { 应用标识 } })
}
function handleDesktopContextMenu(e: MouseEvent) {
  const el = e.target as HTMLElement
  if (el.closest('.桌面窗口') || el.closest('.文件列表区域')) return
  右键.打开(e, 右键.构建桌面壳空白菜单(), { 类型: '桌面壳空白' })
}

function handleContextMenuSelect(键: string) {
  右键.关闭()
  const 上下文 = 右键.上下文.value
  const 应用标识 = (上下文?.目标?.appKey as string) || ''

  // 全局动作
  if (键 === '刷新桌面') { 更新容器尺寸(); return }
  if (键 === '打开开始菜单') { 显示启动器.value = true; return }
  if (键 === '上传文件') { 管理器.打开窗口('desktop'); emit('desktop:upload-file', { 文件夹id: null }); return }
  if (键 === '新建文件夹') { 管理器.打开窗口('desktop'); emit('desktop:create-folder', { 文件夹id: null }); return }
  if (键 === 'openFile管理') { 管理器.打开窗口('desktop'); return }
  if (键 === '打开回收站') { 管理器.打开窗口('recycle'); return }

  // 图标右键：键为 __openApp__ 时，根据上下文里的应用标识打开对应的窗口
  if (键 === '__openApp__' && 应用标识) { 管理器.打开窗口(应用标识); return }
}
function handleSwitchWindow(id: string) {
  const w = 管理器.windows.find(x => x.id === id)
  if (w) {
    if (w.minimized || !w.isActive) { 管理器.激活窗口(id) } else { 管理器.切换最小化(id) }
  }
}
</script>
