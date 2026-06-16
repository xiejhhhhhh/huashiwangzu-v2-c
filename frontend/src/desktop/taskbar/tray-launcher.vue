<template>
  <div class="托盘启动器-包装">
    <button v-for="app in 应用列表" :key="app.appKey" class="托盘启动器-按钮" type="button" :title="app.appName" @click="emit('openApp', app.appKey)">
      <AppIcon :图标="app.icon" :size="18" />
    </button>
  </div>
</template>

<script setup lang="ts">
import AppIcon from '@/desktop/components/app-icon.vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'

const props = defineProps<{ 应用列表: AppRegistryEntry[] }>()
const emit = defineEmits<{ (e: 'openApp', 应用标识: string): void }>()
</script>

<style scoped>
.托盘启动器-包装 { display: flex; align-items: center; gap: 2px; }
.托盘启动器-按钮 {
  width: 24px; height: 24px; border: none; background: transparent; color: #dbeafe;
  cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center;
  opacity: .82; transition: background .12s, opacity .12s;
}
.托盘启动器-按钮:hover { background: rgba(255,255,255,.08); opacity: 1; }
</style>
