<template>
  <div class="桌面图标网格">
    <div
      v-for="应用 in 应用列表"
      :key="应用.appKey"
      class="桌面图标项 桌面应用图标项"
      :class="{ '桌面图标项-选中': 是否选中(`app:${应用.appKey}`) }"
      :data-选中标记="`app:${应用.appKey}`"
      @click="处理应用点击(应用.appKey, $event)"
      @dblclick="$emit('openApp', 应用.appKey)"
      @contextmenu.prevent.stop="$emit('右键应用', 应用.appKey, $event)"
    >
      <div class="桌面图标图像">
        <AppIcon :图标="应用.icon" :size="54" />
      </div>
      <span class="桌面图标标签">{{ 应用.appName }}</span>
    </div>
    <div
      v-for="文件 in 文件列表"
      :key="`file-${文件.id}`"
      class="桌面图标项 桌面文件图标项"
      :class="{
        '桌面图标项-选中': 是否选中(`file:${文件.id}`),
        '桌面图标项-拖拽悬停': 文件.是否为文件夹 && 当前拖拽悬停id === `${文件.id}`,
      }"
      :data-选中标记="`file:${文件.id}`"
      :data-是文件夹="文件.是否为文件夹 ? '' : undefined"
      @mousedown="处理文件拖拽开始(文件, $event)"
      @click="处理文件点击(文件, $event)"
      @dblclick="$emit('openFile', 文件)"
    >
      <div class="桌面图标图像">
        <FileVisualIcon :类型="文件.是否为文件夹 || !文件.格式 ? '文件夹' : '文件'" :扩展名="文件.格式 || ''" :size="48" />
      </div>
      <span class="桌面图标标签">{{ 显示文件名(文件) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import type { FileEntry } from '@/shared/api/types'
import AppIcon from '@/desktop/components/app-icon.vue'
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import { 是否选中, 选中, 追加选中, 取消选中, 选中列表 } from '@/desktop/selection/desktop-selection-state'
import { 开始拖拽, 拖拽状态, 进入文件夹, 离开文件夹, 结束拖拽 } from '@/desktop/drag-drop/drag-state'
import { 取落点样式, 落点覆盖 } from '@/desktop/drag-drop/drag-tool'
import { computed, onMounted } from 'vue'
import { 格式化文件displayName } from '@/shared/files/display-name'
import './desktop-icon-grid.css'

const 当前拖拽悬停id = computed(() => 拖拽状态.dragOverId ? `file:${拖拽状态.dragOverId}` : null)

/* 落点变换：图标渲染完后应用 transform 偏移 */
onMounted(() => {
  requestAnimationFrame(() => {
    document.querySelectorAll('[data-选中标记]').forEach(el => {
      const 标记 = el.getAttribute('data-选中标记')
      if (标记 && 落点覆盖[标记]) {
        (el as HTMLElement).style.transform = 取落点样式(标记)
      }
    })
  })
})

defineProps<{
  应用列表: AppRegistryEntry[]
  文件列表?: FileEntry[]
}>()

defineEmits<{
  (e: 'openApp', 应用标识: string): void
  (e: 'openFile', 文件: FileEntry): void
  (e: '右键应用', 应用标识: string, event: MouseEvent): void
}>()

function 处理应用点击(应用标识: string, e: MouseEvent) {
  const 标记 = `app:${应用标识}`
  if (e.ctrlKey) { 追加选中(标记); return }
  if (是否选中(标记)) return
  选中(标记)
}

function 处理文件点击(文件: FileEntry, e: MouseEvent) {
  const 标记 = `file:${文件.id}`
  if (e.ctrlKey) { 追加选中(标记); return }
  if (是否选中(标记)) return
  选中(标记)
}

function 处理文件拖拽开始(文件: FileEntry, e: MouseEvent) {
  if (e.button !== 0) return  // 只响应左键
  const 标记 = `file:${文件.id}`
  const 已选 = 选中列表.value
  const 拖拽ids = 已选.includes(标记) ? 已选 : [标记]
  if (!已选.includes(标记)) {
    取消选中()
    选中(标记)
  }
  开始拖拽(拖拽ids, e.clientX, e.clientY)
  e.stopPropagation()
}

function 显示文件名(文件: FileEntry) {
  return 文件.是否为文件夹 ? String(文件.文件名 || '') : 格式化文件displayName(文件.文件名, 文件.格式)
}
</script>
