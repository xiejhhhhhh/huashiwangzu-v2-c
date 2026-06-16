<template>
  <span class="应用图标" :style="样式">
    <img v-if="图片地址" class="应用图标图片" :src="图片地址" :alt="图标" />
    <span v-else v-html="svg源码" />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getAppSVG, getApp图片 } from '@/shared/icons/app-icon-assets'

const props = withDefaults(defineProps<{ 图标: string; size?: number }>(), { size: 20 })

const svg源码 = computed(() => getAppSVG(props.图标))
const 图片地址 = computed(() => getApp图片(props.图标))
const 样式 = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
</script>

<style scoped>
.应用图标 { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; }
.应用图标图片 { width: 100%; height: 100%; display: block; object-fit: contain; image-rendering: auto; }
.应用图标 :deep(svg) { width: 100%; height: 100%; display: block; }
.应用图标 :deep(path[fill='currentColor']) { fill: #e2e8f0; }
.应用图标 :deep(path[fill='#212121']), .应用图标 :deep(path[fill='black']), .应用图标 :deep(path[fill='#000']) { fill: #dbeafe; }
</style>
