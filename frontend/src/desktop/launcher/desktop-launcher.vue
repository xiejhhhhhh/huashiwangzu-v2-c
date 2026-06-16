<template>
  <div v-if="显示" class="启动器遮罩" @click.self="emit('关闭')">
    <div class="启动器面板" @click.stop>
      <div class="启动器搜索区"><input v-model="搜索词" class="启动器搜索输入" type="text" placeholder="搜索文件和文件夹..." /></div>
      <div class="启动器头部">开始</div>
      <div class="启动器副标题">已固定</div>
      <div class="启动器网格">
        <div v-for="应用 in 过滤应用列表" :key="应用.appKey" class="启动器应用项" @click="emit('openApp', 应用.appKey)">
          <AppIcon :图标="应用.icon" :size="28" />
          <span class="启动器应用名">{{ 应用.appName }}</span>
        </div>
      </div>
      <div class="启动器副标题 启动器副标题-分割">系统工具</div>
      <button class="启动器工具项" type="button" @click="emit('执行命令', '打开右栏')"><span>📌</span><span>打开右侧功能栏</span></button>
      <button class="启动器工具项" type="button" @click="emit('执行命令', '刷新桌面')"><span>🔄</span><span>刷新桌面</span></button>
      <button class="启动器工具项" type="button" @click="emit('执行命令', '最小化全部')"><span>🪟</span><span>最小化所有窗口</span></button>
      <button class="启动器工具项" type="button" @click="emit('执行命令', '还原全部')"><span>📐</span><span>还原全部窗口</span></button>
      <button class="启动器工具项" type="button" @click="emit('openApp', 'desktop')"><span>📂</span><span>文件管理</span></button>
      <button class="启动器工具项" type="button" @click="emit('openApp', 'recycle')"><span>🗑</span><span>回收站</span></button>
      <div class="启动器底栏">
        <span class="启动器用户">👤 {{ 用户名 }}</span>
        <div class="启动器底栏操作">
          <button class="启动器底栏按钮" type="button" @click="emit('openApp', 'settings')">⚙️</button>
          <button class="启动器底栏按钮" type="button" @click="emit('执行命令', '退出登录')">🚪</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { useUserStore } from '@/platform/stores/user'
import AppIcon from '@/desktop/components/app-icon.vue'

const props = defineProps<{
  显示: boolean
  应用列表: AppRegistryEntry[]
}>()

const emit = defineEmits<{
  (e: 'openApp', 应用标识: string): void
  (e: '执行命令', 命令: string): void
  (e: '关闭'): void
}>()

const 搜索词 = ref('')
const 过滤应用列表 = computed(() => props.应用列表.filter(应用 => !搜索词.value.trim() || 应用.appName.includes(搜索词.value.trim())))
const 用户Store = useUserStore()
const 用户名 = computed(() => 用户Store.用户信息?.displayName || 用户Store.用户信息?.username || '用户')
</script>

<style scoped>
.启动器遮罩 {
  position: absolute; inset: 0; z-index: 9000;
  display: flex; align-items: flex-end; justify-content: flex-start;
  padding: 0 0 48px 8px; background: transparent;
}
.启动器面板 {
  width: 304px; max-height: 540px; overflow: auto; border-radius: 8px;
  background: rgba(32, 32, 36, 0.96); border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.35); padding: 10px; margin-left: 2px;
  backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
}
.启动器搜索区 { padding: 0 0 8px; }
.启动器搜索输入 { width: 100%; padding: 6px 8px; border: none; border-radius: 4px; background: rgba(255,255,255,.06); color: #e2e8f0; font-size: 11px; outline: none; box-sizing: border-box; }
.启动器头部 { color: #f8fafc; font-size: 14px; font-weight: 700; padding: 2px 4px 8px; }
.启动器副标题 { color: rgba(255,255,255,.45); font-size: 11px; padding: 6px 4px; }
.启动器副标题-分割 { margin-top: 8px; border-top: 1px solid rgba(255,255,255,.08); padding-top: 10px; }
.启动器网格 { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 6px; }
.启动器应用项 {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  min-height: 62px; cursor: pointer; border-radius: 8px; color: #e2e8f0;
}
.启动器应用项:hover, .启动器工具项:hover { background: rgba(255,255,255,.08); }
.启动器应用名 { font-size: 10px; max-width: 72px; text-align: center; }
.启动器工具项 {
  width: 100%; border: none; background: transparent; color: #cbd5e1; cursor: pointer;
  font-size: 12px; text-align: left; padding: 8px 10px; border-radius: 6px;
  display: flex; align-items: center; gap: 8px;
}
.启动器底栏 { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,.08); display: flex; justify-content: space-between; align-items: center; }
.启动器用户 { font-size: 11px; color: #cbd5e1; }
.启动器底栏操作 { display: flex; gap: 6px; }
.启动器底栏按钮 { width: 26px; height: 26px; border: none; border-radius: 4px; background: transparent; color: #94a3b8; cursor: pointer; }
.启动器底栏按钮:hover { background: rgba(255,255,255,.08); color: #e2e8f0; }
</style>
