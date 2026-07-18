<template>
  <div class="async-pane-state" :class="{ error: !!error }" role="status">
    <LoaderCircle v-if="!error" :size="24" class="async-pane-spinner" />
    <TriangleAlert v-else :size="24" />
    <strong>{{ error ? title || '加载失败' : title || '正在加载' }}</strong>
    <span>{{ error || description || '正在准备应用内容…' }}</span>
    <button v-if="error" type="button" @click="$emit('retry')">
      <RotateCcw :size="13" />
      重试
    </button>
  </div>
</template>

<script setup lang="ts">
import { LoaderCircle, RotateCcw, TriangleAlert } from 'lucide-vue-next'

defineProps<{
  title?: string
  description?: string
  error?: string
}>()

defineEmits<{ retry: [] }>()
</script>

<style scoped>
.async-pane-state { min-height: 220px; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 24px; color: #8e8e93; text-align: center; }
.async-pane-state svg { color: #0a84ff; }
.async-pane-state strong { color: #3a3a3c; font-size: 13px; font-weight: 650; }
.async-pane-state span { max-width: 420px; font-size: 11px; line-height: 1.5; }
.async-pane-state.error svg { color: #ff453a; }
.async-pane-state button { height: 30px; margin-top: 4px; padding: 0 10px; display: inline-flex; align-items: center; gap: 5px; border: .5px solid rgba(60,60,67,.22); border-radius: 7px; background: #fff; color: #007aff; font: inherit; font-size: 11px; cursor: pointer; }
.async-pane-state button:hover { background: rgba(10,132,255,.08); }
.async-pane-spinner { animation: async-pane-spin .9s linear infinite; }
@keyframes async-pane-spin { to { transform: rotate(360deg); } }
</style>
