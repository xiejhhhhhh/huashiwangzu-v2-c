<template>
  <viewer-shell
    :file-name="fileName"
    app-name="PDF 查看器"
    file-icon="📕"
    :show-download="true"
    :show-zoom-in="true"
    :show-zoom-out="true"
    :show-fit="true"
    @download="handleDownload"
    @zoom-in="zoomIn"
    @zoom-out="zoomOut"
    @fit="fitToWindow"
  >
    <template #toolbar-center>
      <div class="pv-pagenav" v-if="pageCount > 0">
        <button class="vs-btn" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
        <span class="pv-pagenav-info">
          第 <input class="pv-page-input" type="number" :value="currentPage" @change="onPageInput" min="1" :max="pageCount" /> / {{ pageCount }} 页
        </span>
        <button class="vs-btn" :disabled="currentPage >= pageCount" @click="goPage(currentPage + 1)">下一页</button>
        <button class="vs-btn" @click="showSearch = !showSearch" :class="{ active: showSearch }">搜索</button>
      </div>
    </template>
    <div class="pv-container">
      <div v-if="showSearch" class="pv-search-bar">
        <input
          v-model="searchQuery"
          class="pv-search-input"
          placeholder="搜索文本..."
          @keydown.enter="doSearch"
        />
        <button class="vs-btn" @click="doSearch">搜索</button>
        <button class="vs-btn" @click="searchPrev" :disabled="searchMatchCount === 0">▲</button>
        <button class="vs-btn" @click="searchNext" :disabled="searchMatchCount === 0">▼</button>
        <span v-if="searchMatchCount > 0" class="pv-search-count">
          {{ searchIndex + 1 }}/{{ searchMatches.length }}
        </span>
      </div>
      <div v-if="loadError" class="pv-error">{{ loadError }}</div>
      <div v-else class="pv-viewport" ref="viewportRef">
        <canvas v-for="(page, idx) in renderedPages" :key="idx" :ref="(el) => setCanvasRef(idx, el)"></canvas>
      </div>
    </div>
    <template #statusbar>
      <span v-if="pageCount > 0">{{ pageCount }} 页</span>
      <span v-if="pdfScale !== 1 && pageCount > 0"> | 缩放: {{ Math.round(pdfScale * 100) }}%</span>
    </template>
  </viewer-shell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import viewerShell from '@/shared/components/viewer-shell.vue'

const TOKEN_KEY = 'v2_auth_token'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function getPayload(): { fileId: number; fileName: string } | null {
  const p = (window as any).__MODULE_OPEN_FILE_PAYLOAD__
  if (p?.fileId) return { fileId: p.fileId, fileName: p.fileName || '' }
  return null
}

const fileName = ref('')
const fileBlobUrl = ref('')
const pageCount = ref(0)
const currentPage = ref(1)
const pdfScale = ref(1.5)
const loadError = ref('')
const showSearch = ref(false)
const searchQuery = ref('')
const searchMatches = ref<any[]>([])
const searchMatchCount = computed(() => searchMatches.value.length)
const searchIndex = ref(0)
const viewportRef = ref<HTMLElement | null>(null)
const renderedPages = ref<number[]>([])

let pdfDoc: any = null
let canvasRefs: Record<number, HTMLCanvasElement | null> = {}

function setCanvasRef(idx: number, el: any) {
  canvasRefs[idx] = el as HTMLCanvasElement | null
}

async function loadPdf(fid: number) {
  try {
    loadError.value = ''
    const url = `/api/files/download/${fid}`
    const resp = await fetch(url, { headers: authHeaders() })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    fileBlobUrl.value = URL.createObjectURL(blob)

    const pdfjsLib = await import('pdfjs-dist')
    pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.js'
    pdfDoc = await pdfjsLib.getDocument(fileBlobUrl.value).promise
    pageCount.value = pdfDoc.numPages
    renderedPages.value = Array.from({ length: pageCount.value }, (_, i) => i)
    await nextTick()
    renderAllPages()
  } catch (e: any) {
    loadError.value = e.message || 'PDF 加载失败'
  }
}

async function renderAllPages() {
  if (!pdfDoc) return
  const scale = pdfScale.value
  for (let i = 1; i <= pageCount.value; i++) {
    await renderPage(i, scale)
  }
}

async function renderPage(pageNum: number, scale: number) {
  if (!pdfDoc) return
  const page = await pdfDoc.getPage(pageNum)
  const viewport = page.getViewport({ scale })
  const canvas = canvasRefs[pageNum - 1]
  if (!canvas) return
  canvas.width = viewport.width
  canvas.height = viewport.height
  const ctx = canvas.getContext('2d')!
  await page.render({ canvasContext: ctx, viewport }).promise
}

function zoomIn() {
  pdfScale.value = Math.min(pdfScale.value * 1.25, 5)
  nextTick(() => renderAllPages())
}

function zoomOut() {
  pdfScale.value = Math.max(pdfScale.value / 1.25, 0.5)
  nextTick(() => renderAllPages())
}

function fitToWindow() {
  pdfScale.value = 1.5
  nextTick(() => renderAllPages())
}

function goPage(page: number) {
  if (page < 1 || page > pageCount.value) return
  currentPage.value = page
  const el = viewportRef.value?.children[page - 1] as HTMLElement
  if (el) el.scrollIntoView({ behavior: 'smooth' })
}

function onPageInput(e: Event) {
  const val = parseInt((e.target as HTMLInputElement).value)
  if (val >= 1 && val <= pageCount.value) goPage(val)
}

function doSearch() {
  if (!searchQuery.value || !pdfDoc) return
  searchMatches.value = []
  searchIndex.value = 0
  alert('PDF 文本搜索需 pdf.js textContent API，当前为简化版。请使用浏览器自带查找。')
}

function searchPrev() {
  if (searchMatches.value.length === 0) return
  searchIndex.value = (searchIndex.value - 1 + searchMatches.value.length) % searchMatches.value.length
}

function searchNext() {
  if (searchMatches.value.length === 0) return
  searchIndex.value = (searchIndex.value + 1) % searchMatches.value.length
}

function handleDownload() {
  if (!fileBlobUrl.value) return
  const a = document.createElement('a')
  a.href = fileBlobUrl.value
  a.download = fileName.value
  a.click()
}

onMounted(() => {
  const payload = getPayload()
  if (payload && payload.fileId) {
    fileName.value = payload.fileName || 'document.pdf'
    loadPdf(payload.fileId)
  }
})
</script>

<style scoped>
.pv-container {
  width: 100%;
  height: 100%;
  background: #e8e8e8;
  display: flex;
  flex-direction: column;
}

.pv-search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
}

.pv-search-input {
  flex: 1;
  max-width: 300px;
  padding: 5px 10px;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}

.pv-search-input:focus {
  border-color: #2395bc;
}

.pv-search-count {
  font-size: 12px;
  color: #888;
}

.pv-viewport {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.pv-viewport canvas {
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.15);
  background: #fff;
  max-width: 100%;
}

.pv-pagenav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pv-pagenav-info {
  font-size: 13px;
  color: #555;
  white-space: nowrap;
}

.pv-page-input {
  width: 50px;
  padding: 2px 6px;
  border: 1px solid #d0d0d0;
  border-radius: 3px;
  font-size: 13px;
  text-align: center;
  outline: none;
}

.pv-page-input:focus {
  border-color: #2395bc;
}

.pv-error {
  padding: 40px;
  text-align: center;
  color: #e74c3c;
  font-size: 14px;
}
</style>
