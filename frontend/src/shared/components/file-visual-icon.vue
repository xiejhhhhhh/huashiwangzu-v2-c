<template>
  <span class="文件视觉图标" :style="样式" v-html="svg源码" />
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ 类型: '文件' | '文件夹'; size?: number; 扩展名?: string }>(), { size: 20, 扩展名: '' })
const 文件夹图标 = '<svg viewBox="0 0 64 52" xmlns="http://www.w3.org/2000/svg"><path d="M6 12c0-3.3 2.7-6 6-6h12l5 5h23c3.3 0 6 2.7 6 6v4H6v-9z" fill="#9ed0ff"/><path d="M4 18c0-3.3 2.7-6 6-6h44c3.3 0 6 2.7 6 6v20c0 4.4-3.6 8-8 8H12c-4.4 0-8-3.6-8-8V18z" fill="#5aa7ff"/><path d="M7 21h50v3H7z" fill="#cfe7ff" opacity=".65"/></svg>'
const 默认文档 = '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><path d="M16 6h24l10 10v36c0 3.3-2.7 6-6 6H16c-3.3 0-6-2.7-6-6V12c0-3.3 2.7-6 6-6z" fill="#fff" stroke="#d9e2ec" stroke-width="2"/><path d="M40 6v12h12" fill="#eef4fa"/><path d="M18 28h28M18 36h28M18 44h18" stroke="#94a3b8" stroke-width="4" stroke-linecap="round"/></svg>'
const 记事本图标 = '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="12" y="10" width="40" height="48" rx="6" fill="#7dd3fc"/><rect x="12" y="52" width="40" height="6" rx="2" fill="#d97706" opacity=".75"/><path d="M20 10v-4M28 10v-4M36 10v-4M44 10v-4" stroke="#0f172a" stroke-width="4" stroke-linecap="round"/><path d="M21 26h22M21 34h22M21 42h16" stroke="#0c4a6e" stroke-width="4" stroke-linecap="round" opacity=".78"/></svg>'
function 构建Word图标() { return '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="24" y="10" width="30" height="44" rx="4" fill="#2b78da"/><rect x="30" y="10" width="24" height="44" rx="4" fill="#185abd"/><path d="M30 20h24M30 30h24M30 40h24" stroke="#5b9af4" stroke-width="4" opacity=".55"/><rect x="8" y="18" width="24" height="28" rx="4" fill="#185abd"/><text x="20" y="36" text-anchor="middle" font-size="18" font-weight="700" font-family="Arial, sans-serif" fill="#fff">W</text></svg>' }
function 构建Excel图标() { return '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="24" y="10" width="30" height="44" rx="4" fill="#33c481"/><rect x="30" y="10" width="24" height="44" rx="4" fill="#107c41"/><path d="M30 22h24M42 10v44M30 38h24" stroke="#6ee7b7" stroke-width="4" opacity=".38"/><rect x="8" y="18" width="24" height="28" rx="4" fill="#107c41"/><text x="20" y="36" text-anchor="middle" font-size="18" font-weight="700" font-family="Arial, sans-serif" fill="#fff">X</text></svg>' }
function 构建PPT图标() { return '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="28" y="12" width="26" height="40" rx="4" fill="#f59e0b"/><circle cx="41" cy="24" r="8" fill="#fff3"/><path d="M41 24V16A8 8 0 0 1 49 24Z" fill="#fff"/><path d="M34 36h14M34 42h14" stroke="#fff" stroke-width="3.5" stroke-linecap="round" opacity=".85"/><path d="M10 18l20-6v40l-20-6z" fill="#f43f5e"/><text x="20" y="36" text-anchor="middle" font-size="18" font-weight="700" font-family="Arial, sans-serif" fill="#fff">P</text></svg>' }
function 构建徽标文档(底: string, 标签: string, 线: string) { return `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><path d="M16 6h24l10 10v36c0 3.3-2.7 6-6 6H16c-3.3 0-6-2.7-6-6V12c0-3.3 2.7-6 6-6z" fill="#fff" stroke="#d9e2ec" stroke-width="2"/><path d="M40 6v12h12" fill="#eef4fa"/><rect x="14" y="14" width="28" height="12" rx="6" fill="${底}"/><text x="28" y="22.5" text-anchor="middle" font-size="8.5" font-weight="700" font-family="Arial, sans-serif" fill="#fff">${标签}</text><path d="M18 34h24M18 42h24M18 50h16" stroke="${线}" stroke-width="4" stroke-linecap="round" opacity=".7"/></svg>` }
function 构建文档图标(扩展名: string) { const k = 扩展名.toLowerCase(); return ({ txt: 记事本图标, doc: 构建Word图标(), docx: 构建Word图标(), xls: 构建Excel图标(), xlsx: 构建Excel图标(), ppt: 构建PPT图标(), pptx: 构建PPT图标(), pdf: 构建徽标文档('#dc2626', 'PDF', '#dc2626'), png: 构建徽标文档('#0ea5e9', 'PNG', '#0ea5e9'), jpg: 构建徽标文档('#7c3aed', 'JPG', '#7c3aed'), jpeg: 构建徽标文档('#7c3aed', 'JPG', '#7c3aed'), zip: 构建徽标文档('#f59e0b', 'ZIP', '#b45309') } as Record<string, string>)[k] || 默认文档 }
const svg源码 = computed(() => props.类型 === '文件夹' ? 文件夹图标 : 构建文档图标(props.扩展名 || ''))
const 样式 = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
</script>

<style scoped>
.文件视觉图标 { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; }
.文件视觉图标 :deep(svg) { width: 100%; height: 100%; display: block; }
</style>
