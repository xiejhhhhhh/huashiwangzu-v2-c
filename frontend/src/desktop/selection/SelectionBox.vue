<template>
  <div
    v-if="有效"
    class="框选矩形"
    :style="{
      left: 矩形.x + 'px',
      top: 矩形.y + 'px',
      width: 矩形.w + 'px',
      height: 矩形.h + 'px',
    }"
  />
</template>

<script setup lang="ts">
import { 框选有效, 框选矩形 } from './selection-box-state'
const 有效 = 框选有效
const 矩形 = 框选矩形
</script>

<style scoped>
.框选矩形 {
  position: fixed;
  background: rgba(0, 120, 215, 0.12);
  border: 1px solid rgba(0, 120, 215, 0.5);
  pointer-events: none;
  z-index: 9999;
}
</style>
