<template>
  <Teleport to="body">
    <div v-if="显示" class="右栏遮罩" @click.self="emit('关闭')">
      <aside class="右栏面板">
        <div class="右栏头部"><span>📌 {{ 当前标题 }}</span><button class="右栏关闭" type="button" @click="emit('关闭')">✕</button></div>
        <div class="右栏快捷区">
          <button v-for="应用 in 应用列表" :key="应用.appKey" class="右栏快捷项" :class="{ '右栏快捷项-激活': 应用.appKey === 当前应用标识 }" type="button" @click="emit('切换', 应用.appKey)"><AppIcon :图标="应用.icon" :size="18" /><span>{{ 应用.appName }}</span></button>
        </div>
        <iframe class="右栏预览框" :src="当前路径" title="桌面右侧功能栏预览" />
        <div class="右栏底部"><button class="右栏打开按钮" type="button" @click="emit('在窗口打开', 当前应用标识)">在窗口打开</button></div>
      </aside>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import AppIcon from '@/desktop/components/app-icon.vue'

const props = defineProps<{ 显示: boolean; 当前路径: string; 当前应用标识: string; 应用列表: AppRegistryEntry[] }>()
const emit = defineEmits<{ (e: '关闭'): void; (e: '切换', 应用标识: string): void; (e: '在窗口打开', 应用标识: string): void }>()
const 当前标题 = computed(() => props.应用列表.find(x => x.appKey === props.当前应用标识)?.appName || '快捷面板')
</script>

<style scoped>
.右栏遮罩{position:fixed;inset:0;z-index:10001;background:rgba(15,23,42,.12);display:flex;justify-content:flex-end}
.右栏面板{width:min(520px,48vw);height:calc(100vh - 40px);margin-top:0;background:#0f172a;border-left:1px solid rgba(255,255,255,.1);box-shadow:-12px 0 36px rgba(0,0,0,.35);display:flex;flex-direction:column}
.右栏头部{height:38px;display:flex;align-items:center;justify-content:space-between;color:#dbeafe;font-size:12px;padding:0 10px;border-bottom:1px solid rgba(255,255,255,.08);background:rgba(15,23,42,.95)}
.右栏关闭{border:none;background:transparent;color:#cbd5e1;font-size:14px;cursor:pointer}.右栏快捷区{display:flex;gap:6px;padding:10px;border-bottom:1px solid rgba(255,255,255,.08);overflow-x:auto}
.右栏快捷项{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:8px;border:1px solid transparent;background:rgba(255,255,255,.04);color:#dbeafe;cursor:pointer;white-space:nowrap}.右栏快捷项-激活{background:rgba(59,130,246,.16);border-color:rgba(59,130,246,.25)}
.右栏预览框{width:100%;flex:1;border:none;background:#fff}.右栏底部{padding:10px;border-top:1px solid rgba(255,255,255,.08);display:flex;justify-content:flex-end}.右栏打开按钮{border:none;background:#2563eb;color:#fff;border-radius:8px;padding:8px 12px;cursor:pointer}
</style>
