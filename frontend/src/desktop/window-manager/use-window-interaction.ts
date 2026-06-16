import { onUnmounted, ref, type Ref } from 'vue'

type 缩放方向 = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
type 交互配置 = {
  id: string; x: number; y: number; width: number; height: number; maximized: boolean
  minWidth: number; minHeight: number; 根元素: Ref<HTMLElement | null>
  激活: (id: string) => void; 更新位置: (id: string, x: number, y: number) => void
  更新几何: (id: string, x: number, y: number, width: number, height: number) => void
}

const 缩放方向列表: 缩放方向[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

export function use窗口交互(读取配置: () => 交互配置) {
  const 拖拽中 = ref(false), 拖拽起点 = ref({ x: 0, y: 0, winX: 0, winY: 0 })
  const 缩放信息 = ref<{ 方向: 缩放方向; 起点X: number; 起点Y: number; 起始X: number; 起始Y: number; 起始宽: number; 起始高: number } | null>(null)
  const 取边界 = () => {
    const parent = 读取配置().根元素.value?.parentElement
    return { 容器宽: parent?.clientWidth ?? window.innerWidth, 可用高: (parent?.clientHeight ?? window.innerHeight) - 48 }
  }
  function 开始拖拽(e: MouseEvent) {
    const cfg = 读取配置(); if (cfg.maximized) return
    cfg.激活(cfg.id); 拖拽中.value = true
    拖拽起点.value = { x: e.clientX, y: e.clientY, winX: cfg.x, winY: cfg.y }
    document.addEventListener('mousemove', 拖拽移动); document.addEventListener('mouseup', 停止交互)
  }
  function 拖拽移动(e: MouseEvent) {
    if (!拖拽中.value) return
    const cfg = 读取配置(), { 容器宽, 可用高 } = 取边界(), dx = e.clientX - 拖拽起点.value.x, dy = e.clientY - 拖拽起点.value.y
    cfg.更新位置(cfg.id, Math.max(0, Math.min(拖拽起点.value.winX + dx, 容器宽 - cfg.width)), Math.max(0, Math.min(拖拽起点.value.winY + dy, 可用高 - cfg.height)))
  }
  function 开始缩放(方向: 缩放方向, e: MouseEvent) {
    const cfg = 读取配置(); if (cfg.maximized) return
    cfg.激活(cfg.id)
    缩放信息.value = { 方向, 起点X: e.clientX, 起点Y: e.clientY, 起始X: cfg.x, 起始Y: cfg.y, 起始宽: cfg.width, 起始高: cfg.height }
    document.addEventListener('mousemove', 缩放移动); document.addEventListener('mouseup', 停止交互)
  }
  function 缩放移动(e: MouseEvent) {
    if (!缩放信息.value) return
    const cfg = 读取配置(), info = 缩放信息.value, { 容器宽, 可用高 } = 取边界(), dx = e.clientX - info.起点X, dy = e.clientY - info.起点Y
    let { 起始X: x, 起始Y: y, 起始宽: width, 起始高: height } = info
    if (info.方向.includes('e')) width = Math.max(cfg.minWidth, Math.min(info.起始宽 + dx, 容器宽 - info.起始X))
    if (info.方向.includes('s')) height = Math.max(cfg.minHeight, Math.min(info.起始高 + dy, 可用高 - info.起始Y))
    if (info.方向.includes('w')) { x = Math.max(0, Math.min(info.起始X + dx, info.起始X + info.起始宽 - cfg.minWidth)); width = info.起始宽 - (x - info.起始X) }
    if (info.方向.includes('n')) { y = Math.max(0, Math.min(info.起始Y + dy, info.起始Y + info.起始高 - cfg.minHeight)); height = info.起始高 - (y - info.起始Y) }
    cfg.更新几何(cfg.id, Math.round(x), Math.round(y), Math.round(width), Math.round(height))
  }
  function 停止交互() {
    拖拽中.value = false; 缩放信息.value = null
    document.removeEventListener('mousemove', 拖拽移动); document.removeEventListener('mousemove', 缩放移动); document.removeEventListener('mouseup', 停止交互)
  }
  onUnmounted(停止交互)
  return { 缩放方向列表, 开始拖拽, 开始缩放 }
}
